import { DirectionalLight, Group, type Scene } from 'three';

interface DirectionalLightSpec {
  readonly name: string;
  readonly intensity: number;
  readonly position: readonly [number, number, number];
}

const CHARACTER_LIGHTS: readonly DirectionalLightSpec[] = [
  {
    name: 'character-key-light',
    intensity: 2.2,
    position: [4, 6, 5],
  },
  {
    name: 'character-fill-light',
    intensity: 0.8,
    position: [-4, 3, 2],
  },
  {
    name: 'character-rim-light',
    intensity: 1.5,
    position: [0, 5, -5],
  },
];

export function addCharacterReadabilityLighting(scene: Scene): Group {
  const rig = new Group();
  rig.name = 'character-readability-lighting';

  for (const spec of CHARACTER_LIGHTS) {
    const light = new DirectionalLight(0xffffff, spec.intensity);
    light.name = spec.name;
    light.position.set(...spec.position);
    rig.add(light);
  }

  scene.add(rig);
  return rig;
}
