# Usage Examples

## GUI (no Python required after building)

```bat
dist\SpriteExtractor.exe
```

Or from source:

```bash
python sprite_extractor_gui.py
```

## Default: Animated and static GIFs

```bash
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock"
```

## Animations Only

```bash
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock" --animations-only
```

## Static Sprites Only

```bash
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock" --static-only
```

## Write frame metadata files

```bash
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock" --write-frames-txt
```

## Custom Delay

```bash
# Slower animations (100 centiseconds = 1 second per frame).
# Default is the catalog delay, or 50 (500ms) when that value is 0.
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock" --animations-only --delay 100
```

## Pointing to a Deadlock Installation

Using the folder (recommended):

```bash
python extract_deadlock_sprites.py `
  --deadlock-path "D:\Games\Deadlock" `
  --out "my_extracted_sprites"
```

Using explicit file paths:

```bash
python extract_deadlock_sprites.py `
  --exe "D:\Games\Deadlock\deadlock.exe" `
  --dat "D:\Games\Deadlock\SPRITELG.DAT" `
  --out "\path\to\my_extracted_sprites"
```

## Forcing static treatment for image-bank sprites

Some sprites contain banks of same-sized images that the game indexes by state rather than playing as an animation:

```bash
python extract_deadlock_sprites.py --deadlock-path "C:\Games\Deadlock" --static-id 0 --static-id 13 --static-id 14 --static-id 15 --static-id 20
```
