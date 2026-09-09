import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import * as THREE from 'three';
import ComparisonControls, { syncMixerTime } from './ComparisonControls';

describe('ComparisonControls', () => {
  it('does not render when repairedBvhId is null or undefined', () => {
    const handleModeChange = vi.fn();
    const { container } = render(
      <ComparisonControls
        mode="original"
        onModeChange={handleModeChange}
        originalBvhId="orig-123"
        repairedBvhId={null}
      />
    );

    expect(screen.queryByTestId('comparison-controls')).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it('renders mode toggle bar when repairedBvhId is present with Original, Repaired, and Ghost Compare buttons', () => {
    const handleModeChange = vi.fn();
    render(
      <ComparisonControls
        mode="ghost"
        onModeChange={handleModeChange}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
        fps={30}
      />
    );

    expect(screen.getByTestId('comparison-controls')).toBeInTheDocument();
    expect(screen.getByTestId('mode-original-btn')).toHaveTextContent('Original (A)');
    expect(screen.getByTestId('mode-repaired-btn')).toHaveTextContent('Repaired (B)');
    expect(screen.getByTestId('mode-ghost-btn')).toHaveTextContent('Ghost Compare (A/B)');
  });

  it('switches comparison mode when buttons are clicked', () => {
    const handleModeChange = vi.fn();
    render(
      <ComparisonControls
        mode="original"
        onModeChange={handleModeChange}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
      />
    );

    fireEvent.click(screen.getByTestId('mode-repaired-btn'));
    expect(handleModeChange).toHaveBeenCalledWith('repaired');

    fireEvent.click(screen.getByTestId('mode-ghost-btn'));
    expect(handleModeChange).toHaveBeenCalledWith('ghost');

    fireEvent.click(screen.getByTestId('mode-original-btn'));
    expect(handleModeChange).toHaveBeenCalledWith('original');
  });

  it('reflects active styling corresponding to current mode', () => {
    const { rerender } = render(
      <ComparisonControls
        mode="original"
        onModeChange={vi.fn()}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
      />
    );

    expect(screen.getByTestId('mode-original-btn').className).toContain('bg-blue-600');
    expect(screen.getByTestId('mode-repaired-btn').className).not.toContain('bg-emerald-600');
    expect(screen.getByTestId('mode-ghost-btn').className).not.toContain('bg-purple-600');

    rerender(
      <ComparisonControls
        mode="repaired"
        onModeChange={vi.fn()}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
      />
    );
    expect(screen.getByTestId('mode-repaired-btn').className).toContain('bg-emerald-600');

    rerender(
      <ComparisonControls
        mode="ghost"
        onModeChange={vi.fn()}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
      />
    );
    expect(screen.getByTestId('mode-ghost-btn').className).toContain('bg-purple-600');
  });

  it('renders ghost legend in ghost mode with color indicators and sync badge', () => {
    const { rerender } = render(
      <ComparisonControls
        mode="original"
        onModeChange={vi.fn()}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
        fps={60}
      />
    );

    expect(screen.queryByTestId('ghost-legend')).not.toBeInTheDocument();

    rerender(
      <ComparisonControls
        mode="ghost"
        onModeChange={vi.fn()}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
        fps={60}
      />
    );

    const legend = screen.getByTestId('ghost-legend');
    expect(legend).toBeInTheDocument();
    expect(legend).toHaveTextContent('Original Ghost (45%)');
    expect(legend).toHaveTextContent('Repaired Solid');
    expect(legend).toHaveTextContent('Lockstep Sync (60 FPS)');
  });

  it('triggers mode switching via keyboard shortcuts a, b, g and 1, 2, 3', () => {
    const handleModeChange = vi.fn();
    render(
      <ComparisonControls
        mode="original"
        onModeChange={handleModeChange}
        originalBvhId="orig-123"
        repairedBvhId="rep-456"
      />
    );

    fireEvent.keyDown(window, { key: 'b' });
    expect(handleModeChange).toHaveBeenCalledWith('repaired');

    fireEvent.keyDown(window, { key: 'g' });
    expect(handleModeChange).toHaveBeenCalledWith('ghost');

    fireEvent.keyDown(window, { key: 'a' });
    expect(handleModeChange).toHaveBeenCalledWith('original');

    fireEvent.keyDown(window, { key: '2' });
    expect(handleModeChange).toHaveBeenCalledWith('repaired');

    fireEvent.keyDown(window, { key: '3' });
    expect(handleModeChange).toHaveBeenCalledWith('ghost');

    fireEvent.keyDown(window, { key: '1' });
    expect(handleModeChange).toHaveBeenCalledWith('original');
  });

  it('ignores keyboard shortcuts when focus is inside text input', () => {
    const handleModeChange = vi.fn();
    render(
      <div>
        <input data-testid="test-input" type="text" />
        <ComparisonControls
          mode="original"
          onModeChange={handleModeChange}
          originalBvhId="orig-123"
          repairedBvhId="rep-456"
        />
      </div>
    );

    const input = screen.getByTestId('test-input');
    input.focus();

    fireEvent.keyDown(input, { key: 'b' });
    expect(handleModeChange).not.toHaveBeenCalled();
  });

  it('syncMixerTime accurately maps frame to target time and clamps to duration', () => {
    const root = new THREE.Object3D();
    const mixer = new THREE.AnimationMixer(root);
    const clip = new THREE.AnimationClip('TestClip', 3.0, []);
    const action = mixer.clipAction(clip);
    action.play();

    const time = syncMixerTime(mixer, action, 30, 30, 3.0);
    expect(time).toBeCloseTo(1.0);
    expect(action.time).toBeCloseTo(1.0);

    const clampedTime = syncMixerTime(mixer, action, 150, 30, 3.0);
    expect(clampedTime).toBeCloseTo(3.0);
    expect(action.time).toBeCloseTo(3.0);

    const negativeTime = syncMixerTime(mixer, action, -10, 30, 3.0);
    expect(negativeTime).toBe(0);
    expect(action.time).toBe(0);
  });

  it('syncMixerTime handles edge cases like zero fps and zero duration', () => {
    const root = new THREE.Object3D();
    const mixer = new THREE.AnimationMixer(root);
    const clip = new THREE.AnimationClip('ZeroClip', 0, []);
    const action = mixer.clipAction(clip);
    action.play();

    const time = syncMixerTime(mixer, action, 10, 0, 0);
    expect(time).toBe(0);
    expect(action.time).toBe(0);
  });

  it('synchronizes multiple animation mixers in lockstep across frame steps', () => {
    const rootOriginal = new THREE.Object3D();
    const rootRepaired = new THREE.Object3D();

    const mixerOriginal = new THREE.AnimationMixer(rootOriginal);
    const mixerRepaired = new THREE.AnimationMixer(rootRepaired);

    const clipOriginal = new THREE.AnimationClip('OriginalClip', 4.0, []);
    const clipRepaired = new THREE.AnimationClip('RepairedClip', 4.0, []);

    const actionOriginal = mixerOriginal.clipAction(clipOriginal);
    const actionRepaired = mixerRepaired.clipAction(clipRepaired);
    actionOriginal.play();
    actionRepaired.play();

    [0, 15, 30, 45, 60, 120].forEach((frame) => {
      const timeOrig = syncMixerTime(mixerOriginal, actionOriginal, frame, 30, clipOriginal.duration);
      const timeRep = syncMixerTime(mixerRepaired, actionRepaired, frame, 30, clipRepaired.duration);

      expect(timeOrig).toBeCloseTo(timeRep);
      expect(actionOriginal.time).toBeCloseTo(actionRepaired.time);
    });
  });

  it('advances mixer linearly without double-applied playback rate', () => {
    const root = new THREE.Object3D();
    const mixer = new THREE.AnimationMixer(root);
    const clip = new THREE.AnimationClip('SpeedClip', 10.0, []);
    const action = mixer.clipAction(clip);
    action.play();

    action.timeScale = 1.0;
    mixer.update(0.5);
    expect(action.time).toBeCloseTo(0.5);

    mixer.setTime(0);
    action.timeScale = 2.0;
    mixer.update(0.5);
    expect(action.time).toBeCloseTo(1.0);

    mixer.setTime(0);
    action.timeScale = 0.5;
    mixer.update(0.5);
    expect(action.time).toBeCloseTo(0.25);
  });
});
