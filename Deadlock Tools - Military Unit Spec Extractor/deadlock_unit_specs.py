"""
Read military unit specification tables from Deadlock v1.31 deadlock.exe.

Addresses are virtual (image base 0x400000). Field names follow disassembly of
the Unit Orders stat helpers (0x423EAB attack, 0x423F19 defense, 0x423D6C movement).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

DATA_SECTION_FILE_OFF = 0x56400
DATA_SECTION_VA = 0x470000

UNIT_TYPE_TABLE_VA = 0x498540
UNIT_TYPE_STRIDE = 0x18
UNIT_COST_TABLE_VA = 0x498798
UNIT_COST_STRIDE = 0x2C  # 11 x uint32

RACE_NAMES: dict[int, str] = {
    0: "ChCh't",
    1: "Cyth",
    2: "Human",
    3: "Maug",
    4: "Re'lu",
    5: "Tarth",
    6: "Uva Mosk",
}

# Lowercase slugs for CSV columns: {slug}_traits, {slug}_notes
RACE_COLUMN_SLUGS: dict[int, str] = {
    0: "chcht",
    1: "cyth",
    2: "human",
    3: "maug",
    4: "relu",
    5: "tarth",
    6: "uva_mosk",
}

CLASSIFICATION_NAMES: dict[int, str] = {
    0: "unknown_0",
    1: "infantry",
    2: "artillery",
    3: "air",
    4: "sea_transport",
    5: "naval_combat",
    6: "command_corps",
    7: "scout",
    8: "colonizer",
    9: "warhead",
    10: "fortification",
}

BUILD_COST_LABELS = [
    "cost_credits",
    "cost_food",
    "cost_energy",
    "cost_wood",
    "cost_metal",
    "cost_steel",
    "cost_endurium",
    "cost_triidium",
    "cost_electronics",
    "cost_anti_matter",
    "cost_art",
]

_FORTIFICATION_TYPE_IDS = {19, 20, 21}
_MAX_UNIT_TYPE_ID = 24

# In-game racial traits that change effective stats or missions (from manual / known behavior).
# These are not always separate columns in the exe type table.
RACE_TRAIT_NOTES: dict[int, str] = {
    0: "Faster combat movement; scouts can steal resources.",
    1: "Scouts can poison land (halve enemy food).",
    2: "Baseline stats.",
    3: "Faster research; scouts sabotage; scouts harder to catch.",
    4: "Scouts subvert morale; Command Corps can mind-control units.",
    5: "Infantry, artillery, and defenses get attack bonuses; weak scouts/ships.",
    6: "Uva Mosk infantry in some rosters; spyjet-related units.",
}


@dataclass(frozen=True)
class UnitTypeRecord:
    type_id: int
    name: str
    classification_id: int
    classification: str
    credits_word: int
    aux_word: int
    damage_word: int
    movement_base: int
    movement_timer: int
    attack: int
    defense: int
    build_costs: dict[str, int]
    raw_hex: str
    tail_flags_hex: str

    def is_military(self) -> bool:
        return self.classification_id in CLASSIFICATION_NAMES and self.classification_id != 0


def race_column_fieldnames() -> list[str]:
    names: list[str] = []
    for race_id in sorted(RACE_COLUMN_SLUGS):
        slug = RACE_COLUMN_SLUGS[race_id]
        names.append(f"{slug}_traits")
        names.append(f"{slug}_notes")
    return names


def race_columns_for_unit(record: UnitTypeRecord) -> dict[str, str]:
    out: dict[str, str] = {}
    for race_id in sorted(RACE_COLUMN_SLUGS):
        slug = RACE_COLUMN_SLUGS[race_id]
        out[f"{slug}_traits"] = RACE_TRAIT_NOTES.get(race_id, "")
        out[f"{slug}_notes"] = _effective_notes(record, race_id)
    return out


def va_to_file_offset(va: int) -> int:
    if va < DATA_SECTION_VA:
        raise ValueError(f"VA {va:#x} is outside the mapped data section")
    return DATA_SECTION_FILE_OFF + (va - DATA_SECTION_VA)


def read_cstring(data: bytes, va: int, max_len: int = 80) -> str:
    off = va_to_file_offset(va)
    end = data.find(b"\x00", off, off + max_len)
    if end <= off:
        return ""
    raw = data[off:end]
    if not raw or any(c < 9 or c > 126 for c in raw):
        return ""
    return raw.decode("latin-1")


def load_exe_bytes(exe_path: Path) -> bytes:
    path = Path(exe_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_bytes()


def _effective_notes(record: UnitTypeRecord, race_id: int) -> str:
    notes: list[str] = []
    if race_id == 5 and record.classification_id in (1, 2, 10):
        notes.append("Tarth racial attack bonus applies to this unit class in combat.")
    if race_id == 0 and record.classification_id in (1, 2, 3, 5, 7):
        notes.append("ChCh't faster combat movement applies.")
    if race_id == 3 and record.classification_id == 7:
        notes.append("Maug scouts: stronger sabotage / harder to catch.")
    if race_id == 4 and record.classification_id == 7:
        notes.append("Re'lu scouts: subvert morale mission.")
    if race_id == 1 and record.classification_id == 7:
        notes.append("Cyth scouts: poison land mission.")
    if race_id == 0 and record.classification_id == 7:
        notes.append("ChCh't scouts: steal resources mission.")
    if record.classification_id == 6:
        if race_id == 4:
            notes.append("Re'lu Command Corps: mind control.")
        if race_id == 1:
            notes.append("Cyth Command Corps: mind blast.")
    return "; ".join(notes)


def iter_unit_types(data: bytes, *, military_only: bool = True) -> list[UnitTypeRecord]:
    out: list[UnitTypeRecord] = []
    for type_id in range(_MAX_UNIT_TYPE_ID + 1):
        rec_va = UNIT_TYPE_TABLE_VA + type_id * UNIT_TYPE_STRIDE
        off = va_to_file_offset(rec_va)
        if off + UNIT_TYPE_STRIDE > len(data):
            break
        chunk = data[off : off + UNIT_TYPE_STRIDE]
        name_ptr = struct.unpack_from("<I", chunk, 0)[0]
        name = read_cstring(data, name_ptr)
        if not name:
            break
        credits_word, aux_word = struct.unpack_from("<HH", chunk, 4)
        damage_word = struct.unpack_from("<h", chunk, 0xC)[0]
        classification_id = chunk[0xB]
        movement_base = chunk[0x14]
        movement_timer = chunk[0xF]
        attack = chunk[0x15]
        defense = chunk[0x16]
        tail = chunk[0x10:0x18]

        cost_off = va_to_file_offset(UNIT_COST_TABLE_VA + type_id * UNIT_COST_STRIDE)
        costs_raw = struct.unpack_from("<11I", data, cost_off)
        build_costs = {label: int(costs_raw[i]) for i, label in enumerate(BUILD_COST_LABELS)}

        rec = UnitTypeRecord(
            type_id=type_id,
            name=name,
            classification_id=classification_id,
            classification=CLASSIFICATION_NAMES.get(
                classification_id, f"unknown_{classification_id}"
            ),
            credits_word=credits_word,
            aux_word=aux_word,
            damage_word=damage_word,
            movement_base=movement_base,
            movement_timer=movement_timer,
            attack=attack,
            defense=defense,
            build_costs=build_costs,
            raw_hex=chunk.hex(),
            tail_flags_hex=tail.hex(),
        )
        if type_id == 0:
            continue
        if military_only and rec.type_id in _FORTIFICATION_TYPE_IDS:
            continue
        if military_only and not rec.is_military():
            continue
        out.append(rec)
    return out
