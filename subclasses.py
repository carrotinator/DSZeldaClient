from enum import IntEnum
from operator import index
from typing import TYPE_CHECKING
import worlds._bizhawk as bizhawk

if TYPE_CHECKING:
    try:
        from ..Client import PhantomHourglassClient
    except ImportError:
        pass

# Read list of address data
async def read_memory_values(ctx, read_list: dict[str, tuple[int, int, str]], signed=False) -> dict[str, int]:
    keys = read_list.keys()
    read_data = [(a, s, d) for a, s, d in read_list.values()]
    read_result = await bizhawk.read(ctx.bizhawk_ctx, read_data)
    values = [int.from_bytes(i, "little", signed=signed) for i in read_result]
    return {key: value for key, value in zip(keys, values)}


# Read single address
async def read_memory_value(ctx, address: int, size=1, domain="Main RAM", signed=False, silent=False) -> int:
    read_result = await bizhawk.read(ctx.bizhawk_ctx, [(address, size, domain)])
    if not silent:
        print("\tReading memory value", hex(address), size, domain, ", got value",
              hex(int.from_bytes(read_result[0], "little")))
    return int.from_bytes(read_result[0], "little", signed=signed)


# Write single address
async def write_memory_value(ctx, address: int, value: int, domain="Main RAM", incr=None, size=1, unset=False,
                             overwrite=False):
    prev = await read_memory_value(ctx, address, size, domain)
    if incr is not None:
        value = -value if unset else value
        if incr:
            write_value = prev + value
        else:
            write_value = prev - value
        write_value = 0 if write_value <= 0 else write_value
    else:
        if unset:
            print(f"Unseting bit {hex(address)} {hex(value)} with filter {hex(~value)} from prev {hex(prev)} "
                  f"for result {hex(prev & (~value))}")
            write_value = prev & (~value)
        elif not overwrite:
            write_value = prev | value
        else:
            write_value = value
    write_value = split_bits(write_value, size)
    print(f"\tWriting Memory: {hex(address)}, {write_value}, {size}, {domain}, {incr}, {unset}")
    await bizhawk.write(ctx.bizhawk_ctx, [(address, write_value, domain)])
    return write_value


# Write list of values starting from address
async def write_memory_values(ctx, address: int, values: list, domain="Main RAM", overwrite=False, size=4):
    if not overwrite:
        prev = await read_memory_value(ctx, address, len(values), domain)
        new_values = [old | new for old, new in zip(split_bits(prev, size), values)]
        print(f"\tvalues: {new_values}, old: {split_bits(prev, size)}")
    else:
        new_values = values
    await bizhawk.write(ctx.bizhawk_ctx, [(address, new_values, domain)])


# Get address from pointer
async def get_address_from_heap(ctx, pointer, offset=0) -> int:
    m_course = 0
    while m_course == 0:
        m_course = await read_memory_value(ctx, pointer, 4, domain="Data TCM")
    read = await read_memory_value(ctx, m_course - 0x02000000, 4)
    print(f"Got map address @ {hex(read + offset - 0x02000000)}")
    return read + offset - 0x02000000

def storage_key(ctx, key: str):
    return f"{key}_{ctx.slot}_{ctx.team}"

def get_stored_data(ctx, key, default=None):
    store = ctx.stored_data.get(storage_key(ctx, key), default)
    store = store if store is not None else default
    return store

# Split up large values to write into smaller chunks
def split_bits(value, size):
    ret = []
    f = 0xFFFFFFFFFFFFFF00
    for _ in range(size):
        ret.append(value & 0xFF)
        value = (value & f) >> 8
    return ret

all_addresses = []

class Address:
    addr_eu: int
    addr_us: int
    addr: int
    region: str
    domain: str
    size: int
    all_addresses: list = all_addresses

    def __init__(self, addr_eu, addr_us=None, size=1, domain="Main RAM"):
        self.addr_eu = addr_eu
        self.addr_us = addr_us
        self.addr_lookup = [addr_eu, addr_us]
        self.current_region = 0
        self.addr = addr_eu

        self.all_addresses.append(self)
        print(all_addresses)

    def set_region(self, region):
        self.current_region = self._region_int(region)
        self.addr = self.addr_lookup[self.current_region]

    @staticmethod
    def _region_int(region):
        if isinstance(region, str):
            assert region.lower() in ["eu", "us"]
            region = ["eu", "us"].index(region.lower())
        assert region in [0, 1]
        return region

    def get_address(self, region=None):
        if region is not None:
            region = self._region_int(region)
            return self.addr_lookup[region]
        return self.addr

    def get_read_list(self):
        return [(self.addr, self.size, self.domain)]

    def get_write_list(self, value):
        return [(self.addr, split_bits(value, self.size), self.domain)]

    async def get_value(self, ctx, region="eu", silent=True):
        return await read_memory_value(ctx, self.get_address(region), self.size, self.domain, silent=silent)

    def __repr__(self, region="eu"):
        return f"Address Object {hex(self.get_address(region))}"

    def __str__(self):
        return hex(self.get_address())

    async def read(self, ctx, signed=False):
        read_result = await bizhawk.read(ctx.bizhawk_ctx, [(self.addr, self.size, self.domain)])
        return int.from_bytes(read_result[0], "little", signed=signed)

    async def overwrite(self, ctx, value):
        return await bizhawk.write(ctx.bizhawk_ctx, [(self.addr, split_bits(value, self.size), self.domain)])

    async def add(self, ctx, value):
        prev = await self.read(ctx)
        return self.overwrite(ctx, prev + value)

    async def set_bits(self, ctx, value):
        prev = await self.read(ctx)
        return self.overwrite(ctx, prev | value)

    def __add__(self, other):
        return self.addr + other

    def __sub__(self, other):
        return self.addr - other

    def __eq__(self, other):
        return self.addr == other

    def __ne__(self, other):
        return self.addr != other

class DSTransition:
    """
    Datastructures for dealing with Transitions on the client side.
    Not to be confused with PHEntrances, that deals with entrance objects during ER placement.
    """
    entrance_groups: IntEnum | None = None  # set these in game instance or
    opposite_entrance_groups: dict[IntEnum, IntEnum] | None = None

    def __init__(self, name, data):
        self.data = data

        self.name: str = name
        self.id: int | None = data.get("id", None)
        self.entrance: tuple = data.get("entrance", None)
        self.exit: tuple = data.get("exit", None)
        self.entrance_region: str = data["entrance_region"]
        self.exit_region: str = data["exit_region"]
        self.two_way: bool = data.get("two_way", True)
        self.category_group = data["type"]
        self.direction = data["direction"]
        self.island = data.get("island", self.entrance_groups.NONE if self.entrance_groups else None)
        self.coords: tuple | None = data.get("coords", None)
        self.extra_data: dict = data.get("extra_data", {})

        self.stage, self.room, _ = self.entrance if self.entrance else (None, None, None)
        self.scene: int = self.get_scene()
        self.exit_scene: int = self.get_exit_scene()
        self.exit_stage = self.exit[0] if self.exit else None
        self.y = self.coords[1] if self.coords else None

        self.vanilla_reciprocal: DSTransition | None = None  # Paired location

        self.copy_number = 0

    def get_scene(self):
        if self.room:
            return self.stage * 0x100 + self.room
        else:
            return self.stage << 8

    def get_exit_scene(self):
        if self.exit:
            return self.exit[0] * 0x100 + self.exit[1]
        else:
            return None

    def is_pairing(self, r1, r2) -> bool:
        return r1 == self.entrance_region and r2 == self.exit_region

    def get_y(self):
        return self.coords[1] if self.coords else None

    def detect_exit_simple(self, stage, room, entrance):
        return self.exit == (stage, room, entrance)

    def detect_exit_scene(self, scene, entrance):
        return self.exit_scene == scene and entrance == self.exit[2]

    def detect_exit(self, scene, entrance, coords, y_offest):
        if self.detect_exit_scene(scene, entrance):
            if entrance < 0xF0:
                return True
            # Continuous entrance check
            x_max = self.extra_data.get("x_max", 0x8FFFFFFF)
            x_min = self.extra_data.get("x_min", -0x8FFFFFFF)
            z_max = self.extra_data.get("z_max", 0x8FFFFFFF)
            z_min = self.extra_data.get("z_min", -0x8FFFFFFF)
            y = self.coords[1] if self.coords else coords["y"] - y_offest
            # print(f"Checking entrance {self.name}: x {x_max} > {coords['x']} > {x_min}")
            # print(f"\ty: {y + 1000} > {y} > {coords['y'] - y_offest}")
            # print(f"\tz: {z_max} > {coords['z']} > {z_min}")
            if y + 2000 > coords["y"] - y_offest >= y and x_max > coords["x"] > x_min and z_max > coords["z"] > z_min:
                return True
        return False

    def set_stage(self, new_stage):
        self.stage = new_stage
        self.scene = self.get_scene()
        self.entrance = tuple([new_stage] + list(self.entrance[1:]))

    def set_exit_stage(self, new_stage):
        self.exit = tuple([new_stage] + list(self.exit[1:]))
        self.exit_scene = self.get_exit_scene()
        self.exit_stage = self.exit[0]

    def set_exit_room(self, new_room):
        self.exit = tuple([self.exit[0], new_room, self.exit[2]])
        self.exit_scene = self.get_exit_scene()

    def copy(self):
        res = DSTransition(f"{self.name}{self.copy_number+1}", self.data)
        res.copy_number = self.copy_number + 1
        return res

    def __str__(self):
        return self.name

    def debug_print(self):
        print(f"Debug print for entrance {self.name}")
        print(f"\tentrance {self.entrance}")
        print(f"\texit {self.exit}")
        print(f"\tcoords {self.coords}")
        print(f"\textra_data {self.extra_data}")

    @classmethod
    def from_data(cls, entrance_data):
        res = dict()
        counter = {}
        ident = 0
        for name, data in entrance_data.items():
            res[name] = cls(name, data)
            res[name].id = ident
            # print(f"{i} {ENTRANCES[name].entrance_region} -> {ENTRANCES[name].exit_region}")
            ident += 1
            point = data["entrance_region"] + "<=>" + data["exit_region"]
            counter.setdefault(point, 0)
            counter[point] += 1
            if "one_way_data" in data:
                res[name].extra_data |= data["one_way_data"]

            if data.get("two_way", True):
                two_way = True
            else:
                two_way = False
            reverse_name = data.get("return_name", f"Unnamed Entrance {ident}")
            reverse_data = {
                "entrance_region": data.get("reverse_exit_region", data["exit_region"]),
                "exit_region": data.get("reverse_entrance_region", data["entrance_region"]),
                "id": ident,
                "entrance": data.get("exit", data.get("entrance", None)),
                "exit": data["entrance"],
                "two_way": two_way,
                "type": data["type"],
                "island": data.get("return_island", data.get("island", cls.entrance_groups.NONE)),
                "direction": cls.opposite_entrance_groups[data["direction"]],
                "coords": data.get("coords", None),

            }
            if "extra_data" in data:
                reverse_data["extra_data"] = data["extra_data"]
            if "reverse_one_way_data" in data:
                reverse_data.setdefault("extra_data", {})
                reverse_data["extra_data"] = data["reverse_one_way_data"]
            if reverse_name in res:
                print(f"DUPLICATE ENTRANCE!!! {reverse_name}")
            res[reverse_name] = cls(reverse_name, reverse_data)

            res[name].vanilla_reciprocal = res[reverse_name]
            res[reverse_name].vanilla_reciprocal = res[name]

            # print(f"{i} {ENTRANCES[reverse_name].entrance_region} -> {ENTRANCES[reverse_name].exit_region}")
            ident += 1
            point: str = reverse_data["entrance_region"] + "<=>" + reverse_data["exit_region"]
            counter.setdefault(point, 0)
            counter[point] += 1
        return res