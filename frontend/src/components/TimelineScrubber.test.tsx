import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import TimelineScrubber from './TimelineScrubber';
import type { FindingItem } from './DiagnosticCard';

describe('TimelineScrubber', () => {
  const mockIntervals: FindingItem[] = [
    {
      finding_id: 'finding-1',
      joint: 'RightFoot',
      frame_start: 10,
      frame_end: 25,
      time_start: 0.33,
      time_end: 0.83,
      anomaly_type: 'FOOT_SLIP',
      severity: 'CRITICAL',
      explanation: 'Ground penetration on right foot',
    },
    {
      finding_id: 'finding-2',
      joint: 'Spine',
      frame_start: 40,
      frame_end: 60,
      time_start: 1.33,
      time_end: 2.0,
      anomaly_type: 'ACCELERATION_JITTER',
      severity: 'MEDIUM',
      explanation: 'Spine jitter detected',
    },
  ];

  it('renders timeline scrubber and frame counter', () => {
    render(
      <TimelineScrubber
        currentFrame={15}
        totalFrames={100}
        fps={30}
        isPlaying={true}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={mockIntervals}
        onSeek={vi.fn()}
        onTogglePlay={vi.fn()}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={vi.fn()}
      />
    );

    expect(screen.getByTestId('timeline-scrubber')).toBeInTheDocument();
    expect(screen.getByTestId('frame-counter')).toHaveTextContent('15');
    expect(screen.getByTestId('frame-counter')).toHaveTextContent('99');
  });

  it('toggles playback when play-pause button is clicked', () => {
    const handleTogglePlay = vi.fn();
    const { rerender } = render(
      <TimelineScrubber
        currentFrame={0}
        totalFrames={100}
        isPlaying={false}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={vi.fn()}
        onTogglePlay={handleTogglePlay}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={vi.fn()}
      />
    );

    const playPauseBtn = screen.getByTestId('play-pause-btn');
    expect(playPauseBtn).toHaveAttribute('title', 'Play');
    fireEvent.click(playPauseBtn);
    expect(handleTogglePlay).toHaveBeenCalledTimes(1);

    rerender(
      <TimelineScrubber
        currentFrame={0}
        totalFrames={100}
        isPlaying={true}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={vi.fn()}
        onTogglePlay={handleTogglePlay}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={vi.fn()}
      />
    );
    expect(screen.getByTestId('play-pause-btn')).toHaveAttribute('title', 'Pause');
  });

  it('dispatches step forward and step backward controls', () => {
    const handleStepForward = vi.fn();
    const handleStepBackward = vi.fn();

    render(
      <TimelineScrubber
        currentFrame={20}
        totalFrames={100}
        isPlaying={false}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={vi.fn()}
        onTogglePlay={vi.fn()}
        onStepForward={handleStepForward}
        onStepBackward={handleStepBackward}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId('step-forward-btn'));
    expect(handleStepForward).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId('step-back-btn'));
    expect(handleStepBackward).toHaveBeenCalledTimes(1);
  });

  it('toggles loop mode and updates visual styling', () => {
    const handleToggleLoop = vi.fn();
    const { rerender } = render(
      <TimelineScrubber
        currentFrame={0}
        totalFrames={100}
        isPlaying={false}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={vi.fn()}
        onTogglePlay={vi.fn()}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={handleToggleLoop}
        onChangePlaybackRate={vi.fn()}
      />
    );

    const loopBtn = screen.getByTestId('loop-toggle-btn');
    expect(loopBtn).toHaveAttribute('title', 'Loop enabled');
    expect(loopBtn.className).toContain('text-blue-400');
    fireEvent.click(loopBtn);
    expect(handleToggleLoop).toHaveBeenCalledTimes(1);

    rerender(
      <TimelineScrubber
        currentFrame={0}
        totalFrames={100}
        isPlaying={false}
        isLooping={false}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={vi.fn()}
        onTogglePlay={vi.fn()}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={handleToggleLoop}
        onChangePlaybackRate={vi.fn()}
      />
    );
    expect(screen.getByTestId('loop-toggle-btn')).toHaveAttribute('title', 'Loop disabled');
  });

  it('selects playback speed options', () => {
    const handleSpeed = vi.fn();
    render(
      <TimelineScrubber
        currentFrame={0}
        totalFrames={100}
        isPlaying={false}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={vi.fn()}
        onTogglePlay={vi.fn()}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={handleSpeed}
      />
    );

    fireEvent.click(screen.getByTestId('speed-0.5x'));
    expect(handleSpeed).toHaveBeenCalledWith(0.5);

    fireEvent.click(screen.getByTestId('speed-2x'));
    expect(handleSpeed).toHaveBeenCalledWith(2.0);
  });

  it('renders marker bands with correct severity colors', () => {
    const handleSeek = vi.fn();
    const handleSelectInterval = vi.fn();

    render(
      <TimelineScrubber
        currentFrame={0}
        totalFrames={100}
        isPlaying={false}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={mockIntervals}
        onSeek={handleSeek}
        onTogglePlay={vi.fn()}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={vi.fn()}
        onSelectInterval={handleSelectInterval}
      />
    );

    const markers = screen.getAllByTestId('marker-band');
    expect(markers).toHaveLength(2);

    const criticalMarker = markers[0];
    expect(criticalMarker).toHaveAttribute('data-severity', 'critical');
    expect(criticalMarker.className).toContain('bg-red-500');

    const mediumMarker = markers[1];
    expect(mediumMarker).toHaveAttribute('data-severity', 'medium');
    expect(mediumMarker.className).toContain('bg-amber-500');

    fireEvent.click(criticalMarker);
    expect(handleSeek).toHaveBeenCalledWith(10);
    expect(handleSelectInterval).toHaveBeenCalledWith('finding-1', 10);
  });

  it('triggers onSeek on slider range input changes', () => {
    const handleSeek = vi.fn();
    render(
      <TimelineScrubber
        currentFrame={10}
        totalFrames={100}
        isPlaying={false}
        isLooping={true}
        playbackRate={1.0}
        brokenIntervals={[]}
        onSeek={handleSeek}
        onTogglePlay={vi.fn()}
        onStepForward={vi.fn()}
        onStepBackward={vi.fn()}
        onToggleLoop={vi.fn()}
        onChangePlaybackRate={vi.fn()}
      />
    );

    const slider = screen.getByTestId('scrubber-slider');
    fireEvent.change(slider, { target: { value: '45' } });
    expect(handleSeek).toHaveBeenCalledWith(45);
  });
});
