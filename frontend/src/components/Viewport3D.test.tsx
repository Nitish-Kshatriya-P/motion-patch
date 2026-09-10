import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import * as THREE from 'three';
import Viewport3D from './Viewport3D';

vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="mock-three-canvas">{children}</div>
  ),
  useFrame: vi.fn(),
  useThree: () => ({ camera: {}, gl: {} }),
  useLoader: vi.fn().mockImplementation(() => ({
    skeleton: { bones: [new THREE.Bone()] },
    clip: new THREE.AnimationClip('anim', 1, []),
  })),
}));

vi.mock('@react-three/drei', () => ({
  OrbitControls: () => null,
  Grid: () => null,
}));

describe('Viewport3D component', () => {
  it('does not display the file name badge in the 3D renderer', () => {
    const filename = 'custom_test_animation.bvh';
    render(
      <Viewport3D
        bvhId="bvh-123"
        filename={filename}
        totalFrames={100}
        fps={30}
      />
    );

    expect(screen.queryByText(filename)).not.toBeInTheDocument();
  });
});
