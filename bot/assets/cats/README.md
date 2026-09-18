# Cat Asset Library

Catibot cat art is organized by **breed / age stage / state**:

```text
bot/assets/cats/<breed>/<age_stage>/<state>.png
```

Example:

```text
bot/assets/cats/siamese/kitten/idle.png
bot/assets/cats/siamese/kitten/sleep.png
bot/assets/cats/orange_tabby/senior/hungry.png
```

## Official vocabulary

Breeds:

- `orange_tabby`
- `black`
- `siamese`
- `british_shorthair_grey`
- `calico`
- `white`

Age stages:

- `kitten`
- `junior`
- `adult`
- `senior`

States:

- `idle`
- `happy`
- `hungry`
- `feed`
- `play`
- `walk`
- `talk`
- `sleep`
- `angry`
- `sick`

Use lowercase snake_case exactly as written above. PNG with transparent background is the canonical format.

## Catibot Art Style v1

Every official cat asset must use the same visual language:

- 2D hand-drawn semi-realistic cartoon cat
- realistic feline anatomy
- soft painterly/cel shading
- muted warm colors
- restrained thin linework
- expressive but natural eyes
- simplified fur shapes
- full body
- 1:1 composition
- transparent background
- stable cat identity across ages and states

Do not use:

- 3D rendering
- chibi proportions
- photorealism
- flat vector art
- exaggerated oversized eyes

## Anchor workflow

For every `breed + age_stage` combination, create `idle.png` first. It is the
**identity anchor** for that cat at that age.

All other state assets for the same breed and age must be derived from that
anchor. Preserve coat markings, face structure, eye color, body proportions,
ear shape, tail characteristics, and other identity-defining details. Change
only pose, expression, action, and condition as needed for the target state.

When moving between age stages, keep the same recognizable cat identity while
changing age-appropriate proportions and features.

## Runtime lookup and fallback

The canonical runtime key is:

```text
breed:age_stage:state
```

Example:

```text
siamese:kitten:sleep
```

Runtime media lookup uses this fallback order:

1. requested `breed + age_stage + state`
2. same `breed + adult + state`
3. legacy `breed + state`
4. generic `state`

Legacy state aliases are supported:

- `status -> idle`
- `cat_angry_sleep -> angry`

Existing JSON media entries such as `siamese:sleep` remain valid.

## Adding a new asset

1. Choose one supported breed, age stage, and state.
2. Confirm the `idle.png` anchor for that breed and age exists or create it first.
3. Produce the new state from that anchor using Catibot Art Style v1.
4. Export it as a square transparent PNG.
5. Save it at `bot/assets/cats/<breed>/<age_stage>/<state>.png`.
6. Run the asset-library audit/tests before merging.

Do not add empty placeholder PNG files. Missing assets are intentionally handled
by runtime fallbacks until the library is complete.
