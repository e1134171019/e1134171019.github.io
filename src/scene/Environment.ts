import {
  Color,
  Mesh,
  MeshStandardMaterial,
  PlaneGeometry,
  type Scene,
} from 'three';

export interface CharacterEnvironment {
  readonly ground: Mesh<PlaneGeometry, MeshStandardMaterial>;
  readonly background: Color;
}

export function createCharacterEnvironment(scene: Scene): CharacterEnvironment {
  const background = new Color(0x0b0d12);
  const ground = new Mesh(
    new PlaneGeometry(20, 20),
    new MeshStandardMaterial({
      color: 0x17191f,
      metalness: 0,
      roughness: 0.95,
    }),
  );

  ground.name = 'character-ground';
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;

  scene.background = background;
  scene.add(ground);

  return {
    ground,
    background,
  };
}
