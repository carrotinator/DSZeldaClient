from enum import IntEnum

from worlds.tloz_ph.DSZeldaClient.DSZeldaClient import read_memory_value


class DSItem:
    items = {}

    def __init__(self, name, data):
        self.name = name
        self.data = data
        self.id = data["id"]
        self.classification = data["classification"]
        self.items[name] = self

        # Write info
        self.address = data.get("address", None)
        self.value = data.get("value", None)
        self.size = data.get("size", None)
        self.progressive = data.get("progressive", None)

        # Ammo info
        self.ammo_address = data.get("ammo_address", None)
        self.give_ammo = data.get("give_ammo", None)

        # Operation tags
        self.incremental = data.get("incremental", None)
        self.max = data.get("max", None)
        self.progressive_overwrite = data.get("progressive_overwrite", None)

        self.dummy = data.get("dummy", False)
        self.always_process = data.get("always_process", None)

        # data for loading the items bar
        self.inventory_id = data.get("inventory_id", None)

        # Bonus Operations
        self.set_bit = data.get("set_bit", None)
        self.set_bit_in_room = data.get("set_bit_in_room", None)
        self.hint_on_receive = data.get("hint_on_receive", None)

        # Other tags
        self.refill = data.get("refill", None)
        self.ship_part = data.get("ship_part", None)
        self.backup_filler = data.get("backup_filler", None)
        self.dungeon = data.get("dungeon", None)
        self.treasure = data.get("treasure", None)
        self.ship = data.get("ship", None)

        # Item groups
        self.item_groups = data.get("item_groups", None)

    async def normal_item(self, ctx):
        current_value = await read_memory_value(ctx, self.address, self.size)
        return self.address, current_value | self.value, "Main RAM"

    async def incremental_item(self, ctx):
        new_value = await read_memory_value(ctx, self.address, self.size) + self.value
        new_value = self.max if new_value > self.max else new_value
        return self.address, new_value, "Main RAM"

    async def vanilla_item(self, ctx, last_vanilla_item):
        pass

    def determine_write_function(self, ctx, last_vanilla_item):
        if last_vanilla_item and self.name == last_vanilla_item[-1] and not self.always_process:
            pass

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
            return self.stage << 2

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