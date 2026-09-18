# Catibot Art Style v1 — Style Lock

This file freezes the production rules for Catibot cat assets so future states,
ages, and breeds stay visually consistent.

## Canonical style

- 2D hand-drawn semi-realistic cartoon cat
- realistic feline anatomy
- soft painterly / cel shading
- muted warm colors
- restrained thin linework
- expressive but natural eyes
- simplified fur shapes
- full body
- square 1:1 composition
- transparent background
- no environment, text, watermark, accessories, bowls, or toys

Avoid:

- 3D rendering
- chibi proportions
- photorealism
- flat vector rendering
- oversized anime eyes
- exaggerated expressions
- cropped body parts

## Identity-anchor rule

Every `breed + age_stage` combination starts with an `idle.png` anchor.

All later states for that same breed and age must derive from the anchor rather
than independently redesigning the cat. Preserve the face, fur markings, eye
color, proportions, ear shape, paws, and tail identity.

Across age stages, preserve recognizable identity while applying natural
age-appropriate anatomical changes.

## Siamese adult anchor lock

Canonical slot:

```text
bot/assets/cats/siamese/adult/idle.png
```

The approved Siamese adult identity uses:

- slender adult body
- cream-colored body fur
- dark brown face mask
- dark brown ears
- dark brown tail
- dark brown paws
- almond-shaped blue / blue-green eyes
- short smooth coat
- refined graceful silhouette
- calm neutral sitting pose
- gentle 3/4 front view
- relaxed, memorable face design

The cat should occupy roughly 70–80% of the square canvas with comfortable
padding around ears, paws, and tail.

This slot is the reference identity for all future Siamese adult states:
`happy`, `hungry`, `feed`, `play`, `walk`, `talk`, `sleep`,
`angry`, and `sick`.

Do not alter breed markings or redesign the face between states.
