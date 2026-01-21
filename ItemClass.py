
from typing import TYPE_CHECKING
from .subclasses import read_memory_value, split_bits
from ..data.Constants import DUNGEON_KEY_DATA

if TYPE_CHECKING:
    from BaseClasses import ItemClassification
    from worlds._bizhawk.context import BizHawkClientContext
    from .DSZeldaClient import DSZeldaClient


# Handle Small Keys
async def receive_small_key(client: "DSZeldaClient", ctx: "BizHawkClientContext", item: "DSItem", num_received_items):
    res = []
    async def write_keys_to_storage(dungeon) -> tuple[int, list, str]:
        key_data = DUNGEON_KEY_DATA[dungeon]  # TODO: Add dungeon key data to item_data
        prev = await read_memory_value(ctx, key_data["address"])
        bit_filter = key_data["filter"]
        new_v = prev | bit_filter if (prev & bit_filter) + key_data[
            "value"] > bit_filter else prev + key_data["value"]
        print(f"Writing {key_data['name']} key to storage: {hex(prev)} -> {hex(new_v)}")
        return key_data["address"], [new_v], item.domain

    # Get key in own dungeon
    if client.current_stage == item.dungeon:
        print("In dungeon! Getting Key")
        client.key_value = await read_memory_value(ctx, client.key_address)
        client.key_value = 7 if client.key_value > 7 else client.key_value
        res.append((client.key_address, [client.key_value + 1], item.domain))
        res += await client.receive_key_in_own_dungeon(ctx, item.name, write_keys_to_storage)  # TODO: Move special operation here too

    # Get key elsewhere
    else:
        res.append(await write_keys_to_storage(item.dungeon))

    # Extra key operations, in ph writing totok midway keys
    res += await client.received_special_small_keys(ctx, item.name, write_keys_to_storage)

async def receive_refill(client: "DSZeldaClient", ctx: "BizHawkClientContext", item: "DSItem", num_received_items):
    res = []
    prog_received = min(client.item_count(ctx, item.refill, num_received_items),
                        len(item.give_ammo)) - 1
    if prog_received >= 0:
        res.append((item.address, [item.give_ammo[prog_received]], item.domain))
    return res

# Handle progressive and incremental items.
# TODO Split progressive and incremental?
async def receive_normal(client: "DSZeldaClient", ctx: "BizHawkClientContext", item: "DSItem", num_received_items):
    prog_received = 0
    item_value = 0
    res = []
    if hasattr(item, "progressive"):
        prog_received = min(client.item_count(ctx, item.name, num_received_items),
                            len(item.progressive) - 1)
        item_address, item_value = item.progressive[prog_received]
    else:
        item_address = item.address

    # Read address item is to be written to
    prev_value = await read_memory_value(ctx, item_address, size=item.size)

    # Handle different writing operations
    if "incremental" in item.tags:
        if type(item.value) is str:
            value = await client.received_special_incremental(ctx, item)  # TODO: hook into this somehow?
        else:
            value = item.value

            # Heal on heart container
            if item.name == "Heart Container":
                await client.full_heal(ctx)

        item_value = prev_value + value
        item_value = 0 if item_value <= 0 else item_value
        if "Rupee" in item.name:
            item_value = min(item_value, 9999)
        if item.size > 1:
            item_value = split_bits(item_value, item.size)
        if hasattr(item, "max") and item_value > item.max:
            item_value = min(item.max, prev_value)
    elif hasattr(item, "progressive"):
        if "progressive_overwrite" in item.tags and prog_received >= 1:
            item_value = item_value  # Bomb upgrades need to overwrite of everything breaks
        else:
            item_value = prev_value | item_value
    else:
        item_value = prev_value | item.value

    item_values = item_value if type(item_value) is list else [item_value]
    item_values = [min(255, i) for i in item_values]
    res.append((item_address, item_values, item.domain))

    # Handle special item conditions
    if hasattr(item, "give_ammo"):
        res.append((item.ammo_address, [item.give_ammo[prog_received]], item.domain))
    if hasattr(item, "set_bit"):
        for adr, bit in item.set_bit:
            bit_prev = await read_memory_value(ctx, adr)
            res.append((adr, [bit | bit_prev], item.domain))

    return res

async def remove_vanilla_small_key(client: "DSZeldaClient", ctx: "BizHawkClientContext", item: "DSItem", num_received_items):
    address = client.key_address = await client.get_small_key_address(ctx)
    prev_value = await read_memory_value(ctx, address)
    return [(address, [prev_value-1], item.domain)]

async def remove_vanilla_progressive(client: "DSZeldaClient", ctx: "BizHawkClientContext", item: "DSItem", num_received_items):
    res = []
    index = client.item_count(ctx, item.name, num_received_items)
    if index >= len(item.progressive):
        return res
    address, value = item.progressive[index]
    if hasattr(item, "give_ammo"):
        ammo_v = item.give_ammo[min(max(index - 1, 0), len(item.give_ammo) - 1)]
        res.append((item.ammo_address, [ammo_v], item.domain))
    # Progressive overwrite fix
    if "progressive_overwrite" in item.tags and index > 1:
        res.append(
            (item.progressive[index - 1][0], [item.progressive[index - 1][1]], item.domain))
    return res

async def remove_vanilla_normal(client: "DSZeldaClient", ctx: "BizHawkClientContext", item: "DSItem", num_received_items):
    address, value = item.address, item.value

    # Catch vanilla rupees going over 9999
    if "Rupee" in item.name:
        if client.prev_rupee_count + value > 9999:
            value = 9999 - client.prev_rupee_count

    prev_value = await read_memory_value(ctx, address, size=item.size)
    if "incremental" in item.tags:
        value = prev_value - value
    else:
        value = prev_value & (~value)
    return [(item.address, split_bits(value, item.size), item.domain)]


class DSItem:
    """
    Datastructure for item data
    """
    id: int
    classification: "ItemClassification"

    # Basics
    address: int
    value: int
    size: int or str
    progressive: list[tuple]
    domain: str

    # Ammo
    ammo_address: int
    give_ammo: list[int]  # Ammo amount for each upgrade stage
    refill: str  # item reference for refill data

    # Extra bits
    set_bit: list[tuple]
    set_bit_in_room: dict[int, list]

    dungeon: int or bool  # dungeon stage
    ship: int  # index in constants.ships

    # Tags and flags
    dummy: bool
    tags: list[str]
    # always_process: bool  # process item removal even when vanilla
    # incremental: bool
    # ship_part: bool
    # treasure: bool
    # progressive_overwrite: bool  # for progressive items that error if you keep the old bits
    # backup_filler: bool

    overflow_item: str
    max: int  # only used for salvage, and is weird there.
    inventory_id: int  # used for creating item menu on first item

    disconnect_entrances: list[str]  # list of entrances to attempt to disconnect on receive
    hint_on_receive: list[str]  # list of items to hint for on receive

    def __init__(self, name, data, all_items):
        self.data = data
        self.name: str = name
        self.all_items = all_items

        self.value = 1
        self.size = 1
        self.domain = "Main RAM"
        self.tags = []

        for attribute, value in data.items():
            self.__setattr__(attribute, value)

        self.receive_item_func = self.get_receive_function()
        self.remove_vanilla_func = self.get_remove_vanilla_function()

    def get_receive_function(self):
        if "Small Key" in self.name:
            return receive_small_key
        if hasattr(self, "refill"):
            return receive_refill
        if hasattr(self, "address") or hasattr(self, "progressive"):
            return receive_normal

        return None

    def get_remove_vanilla_function(self):
        if hasattr(self, "dummy"):
            return lambda *args: []
        if "Small Key" in self.name:
            return remove_vanilla_small_key
        if hasattr(self, "progressive"):
            return remove_vanilla_progressive
        return remove_vanilla_normal

    def receive_item(self, client: "DSZeldaClient", ctx: "BizHawkClientContext", num_received_items: int):
        return self.receive_item_func(client, ctx, self, num_received_items)

    def remove_vanilla(self, client: "DSZeldaClient", ctx: "BizHawkClientContext", num_received_items):
        return self.remove_vanilla_func(client, ctx, self, num_received_items)

    def get_count(self, ctx, items_received=-1) -> int:
        items_received = len(ctx.items_received) if items_received == -1 else items_received
        return sum([1 for i in ctx.items_received[:items_received] if i.item == self.id])

    def post_process(self, client: "DSZeldaClient", ctx: "BizHawkClientContext"):
        return
