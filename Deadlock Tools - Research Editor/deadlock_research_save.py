"""Parse and patch the technology research table in Deadlock .SAV files."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

TECH_COUNT = 36
TECH_RECORD_SIZE = 0x12
SECTION5_SIZE = 0x2F4
PLAYER_SLOT_COUNT = 7
RESEARCHED_PROGRESS = 150
BASELINE_PROGRESS = 100

RACE_NAMES: dict[int, str] = {
    0: "ChCh't",
    1: "Cyth",
    2: "Human",
    3: "Maug",
    4: "Re'lu",
    5: "Tarth",
    6: "Uva Mosk",
}

# Catalog order matches deadlock.exe table at 0x498BE4 (index 0 = Nothing).
TECHNOLOGY_CATALOG: list[tuple[str, int, int]] = [
    ("Nothing", 0, 0),
    ("Nuclear Fusion", 1, 50),
    ("Synthetic Fertilizer", 1, 50),
    ("Electronics", 1, 50),
    ("Metallurgy", 1, 50),
    ("Fusion Cannon", 2, 100),
    ("Shockwave Projector", 2, 100),
    ("Molecular Bonding", 2, 100),
    ("Surface to Air Missiles", 2, 100),
    ("Rocketry", 2, 100),
    ("Chaos Computers", 2, 100),
    ("Automation", 2, 100),
    ("Hoverway", 2, 100),
    ("Anti-Matter Containment", 3, 250),
    ("Energy Deflectors", 3, 250),
    ("Endurium Mining", 3, 250),
    ("Starflare Bombs", 3, 250),
    ("Neutrionic Fuel", 3, 250),
    ("Artificial Intelligence", 3, 250),
    ("Anti-Matter Rifles", 4, 500),
    ("Ion Weapons", 4, 500),
    ("Triidium Processing", 4, 500),
    ("Orbital Surveillance", 4, 500),
    ("Metal Replication", 4, 500),
    ("Cortex Scanner", 4, 500),
    ("Disruptor Beams", 5, 1000),
    ("Food Replication", 5, 1000),
    ("Anti-Matter Deflectors", 5, 1000),
    ("Sub-Space Scanner", 5, 1000),
    ("Assault Armor", 5, 1000),
    ("Cloaking", 5, 1000),
    ("Anti-Matter Beams", 6, 2000),
    ("Advanced Cloaking", 6, 2000),
    ("Uncloaking", 6, 2000),
    ("Transporters", 7, 5000),
    ("Time Dilation", 8, 5000),
]


@dataclass
class PlayerSlotInfo:
    slot: int
    race_id: int
    label: str


@dataclass
class TechnologyState:
    index: int
    name: str
    tier: int
    cost: int
    known_mask: int
    stolen_mask: int
    progress: list[int] = field(default_factory=lambda: [0] * PLAYER_SLOT_COUNT)


@dataclass
class LoadedTechSave:
    path: Path | None
    data: bytes
    player_count: int
    human_slot: int
    players: list[PlayerSlotInfo]
    technologies: list[TechnologyState]
    technology_offset: int

    @classmethod
    def from_bytes(cls, data: bytes, path: Path | None = None) -> LoadedTechSave:
        players, player_count, human_slot = read_player_slots(data)
        technology_offset = technology_section_offset(data)
        technologies = read_technologies(data, technology_offset)
        return cls(
            path=path,
            data=data,
            player_count=player_count,
            human_slot=human_slot,
            players=players,
            technologies=technologies,
            technology_offset=technology_offset,
        )

    @classmethod
    def from_path(cls, path: Path) -> LoadedTechSave:
        return cls.from_bytes(load_save(path), path.resolve())

    def to_bytes(self) -> bytes:
        return write_technologies(self.data, self.technology_offset, self.technologies)


def load_save(path: Path) -> bytes:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Save file not found: {path}")
    if path.suffix.lower() != ".sav":
        raise ValueError(f"Expected a .SAV file, got: {path.name}")
    return path.read_bytes()


def technology_section_offset(data: bytes) -> int:
    section2 = data[0x7A : 0x7A + 0x6A]
    section4_count = struct.unpack_from("<I", section2, 12)[0]
    offset = 0x7A + 0x6A + 0x14
    offset += section4_count * 0x1092
    offset += SECTION5_SIZE
    end = offset + TECH_COUNT * TECH_RECORD_SIZE
    if end > len(data):
        raise ValueError(
            f"Technology section overruns file (need 0x{end:X}, file is 0x{len(data):X})"
        )
    return offset


def race_name(race_id: int) -> str:
    if race_id in RACE_NAMES:
        return RACE_NAMES[race_id]
    if race_id >= 32:
        return "(empty)"
    return f"Race {race_id}"


def read_player_slots(data: bytes) -> tuple[list[PlayerSlotInfo], int, int]:
    section2 = data[0x7A : 0x7A + 0x6A]
    player_count = struct.unpack_from("<I", section2, 12)[0]
    if player_count < 1 or player_count > PLAYER_SLOT_COUNT:
        raise ValueError(f"Unexpected player count in save: {player_count}")
    human_slot = section2[0x1A]
    players: list[PlayerSlotInfo] = []
    for slot in range(player_count):
        race_id = section2[0x1B + slot]
        label = f"Player {slot} - {race_name(race_id)}"
        if slot == human_slot:
            label += " (human)"
        players.append(PlayerSlotInfo(slot=slot, race_id=race_id, label=label))
    return players, player_count, human_slot


def unpack_technology_record(rec: bytes) -> tuple[int, int, list[int]]:
    if len(rec) != TECH_RECORD_SIZE:
        raise ValueError(f"Technology record must be {TECH_RECORD_SIZE} bytes")
    known_mask, stolen_mask = struct.unpack_from("<HH", rec, 0)
    progress = list(struct.unpack_from("<7H", rec, 4))
    return known_mask, stolen_mask, progress


def pack_technology_record(
    known_mask: int,
    stolen_mask: int,
    progress: list[int],
) -> bytes:
    rec = bytearray(TECH_RECORD_SIZE)
    struct.pack_into("<HH", rec, 0, known_mask & 0xFFFF, stolen_mask & 0xFFFF)
    for index, value in enumerate(progress[:PLAYER_SLOT_COUNT]):
        struct.pack_into("<H", rec, 4 + index * 2, value & 0xFFFF)
    return bytes(rec)


def read_technologies(data: bytes, offset: int) -> list[TechnologyState]:
    technologies: list[TechnologyState] = []
    for index in range(TECH_COUNT):
        rec = data[offset + index * TECH_RECORD_SIZE : offset + (index + 1) * TECH_RECORD_SIZE]
        known_mask, stolen_mask, progress = unpack_technology_record(rec)
        name, tier, cost = TECHNOLOGY_CATALOG[index]
        technologies.append(
            TechnologyState(
                index=index,
                name=name,
                tier=tier,
                cost=cost,
                known_mask=known_mask,
                stolen_mask=stolen_mask,
                progress=progress,
            )
        )
    return technologies


def write_technologies(
    data: bytes,
    offset: int,
    technologies: list[TechnologyState],
) -> bytes:
    if len(technologies) != TECH_COUNT:
        raise ValueError(f"Expected {TECH_COUNT} technology records, got {len(technologies)}")
    patched = bytearray(data)
    for tech in technologies:
        rec = pack_technology_record(tech.known_mask, tech.stolen_mask, tech.progress)
        start = offset + tech.index * TECH_RECORD_SIZE
        patched[start : start + TECH_RECORD_SIZE] = rec
    return bytes(patched)


def is_researched(tech: TechnologyState, slot: int) -> bool:
    if tech.index == 0:
        return False
    if slot < 0 or slot >= PLAYER_SLOT_COUNT:
        return False
    if (tech.known_mask >> slot) & 1:
        return True
    return tech.progress[slot] >= RESEARCHED_PROGRESS


def set_researched(tech: TechnologyState, slot: int, researched: bool) -> None:
    if tech.index == 0:
        return
    if slot < 0 or slot >= PLAYER_SLOT_COUNT:
        return
    bit = 1 << slot
    if researched:
        tech.known_mask |= bit
        if tech.progress[slot] < RESEARCHED_PROGRESS:
            tech.progress[slot] = RESEARCHED_PROGRESS
    else:
        tech.known_mask &= ~bit
        if tech.progress[slot] >= RESEARCHED_PROGRESS:
            tech.progress[slot] = BASELINE_PROGRESS


def editable_technologies(technologies: list[TechnologyState]) -> list[TechnologyState]:
    return [tech for tech in technologies if tech.index > 0]
