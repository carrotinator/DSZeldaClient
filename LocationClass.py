from .subclasses import Address
from dataclasses import dataclass
from typing import Iterable

@dataclass
class DSLocation:
    name: str
    id: int
    scenes: set[int] | int | None = None
    region: str = ""
    from_entrances: list[int] | None = None

    vanilla_item: str = ""
    item_override: str = ""

    y: int | None = None
    x_max: int | None = None
    x_min: int | None = None
    z_max: int | None = None
    z_min: int | None = None

    address: Address | None = None
    value: int | None = None
    chest_offset: int | None = None
    gift_addr: Address | str | list[Address] | None = None
    exact_read: bool = False
    do_special: str | dict = ""
    read_object: bool = False  # read the chest opening instead of normal triggers
    set_bit: list[Iterable] | None = None

    delay_reset: bool = False  # don't reset vanilla item from this location until getting another location or changing scene
    delay_pickup: str | list[str] = ""
    conditional: bool | str = False
    farmable: bool = False
    slot_data: list[Iterable] | None = None
    reload_chests: bool = False
    persistent: bool = False

    dungeon: str = ""  # for in_own_dungeon gen and dungeon exclusion
    boss_room: str = ""
    post_dungeon: str = ""
    boss_reward_location: bool = False
    island_shop: bool = False

    hint_entrance: str | list[str] = ""
    hint_entrance_secondary: str | list[str] = ""

    sram_addr: Address | None = None
    sram_value: int | None = None

    def __post_init__(self):
        if isinstance(self.scenes, int):
            self.scenes = {self.scenes}

    # def __init__(self, name, **kwargs):
    #     self.name = name
    #
    #     for key, value in kwargs.items():
    #         if key not in self.__annotations__:
    #             print(f"Unknown location attribute: {key}: {value}")
    #         setattr(self, key, value)

    def get(self, attribute, default=False):
        return getattr(self, attribute, default)