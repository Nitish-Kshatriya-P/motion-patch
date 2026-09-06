import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import MultimodalPromptBar from './MultimodalPromptBar';

describe('MultimodalPromptBar', () => {
  it('renders input elements and keyboard shortcut badge', () => {
    const onSend = vi.fn();
    const onUpload = vi.fn();

    render(<MultimodalPromptBar onSendMessage={onSend} onFileUpload={onUpload} />);

    expect(screen.getByPlaceholderText(/Ask MotionPatch AI or describe kinematic adjustments/i)).toBeInTheDocument();
    expect(screen.getByTitle('Attach .bvh file')).toBeInTheDocument();
    expect(screen.getByTitle('Send message')).toBeInTheDocument();
    expect(screen.getByText('↵')).toBeInTheDocument();
  });

  it('submits message on Enter keypress and clears input', () => {
    const onSend = vi.fn();
    const onUpload = vi.fn();

    render(<MultimodalPromptBar onSendMessage={onSend} onFileUpload={onUpload} />);

    const textarea = screen.getByPlaceholderText(/Ask MotionPatch AI or describe kinematic adjustments/i);
    fireEvent.change(textarea, { target: { value: 'Fix spine trajectory jitter' } });

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    expect(onSend).toHaveBeenCalledWith('Fix spine trajectory jitter', null);
    expect(textarea).toHaveValue('');
  });

  it('submits message on Cmd+Enter keypress even when shift is pressed or multiline', () => {
    const onSend = vi.fn();
    const onUpload = vi.fn();

    render(<MultimodalPromptBar onSendMessage={onSend} onFileUpload={onUpload} />);

    const textarea = screen.getByPlaceholderText(/Ask MotionPatch AI or describe kinematic adjustments/i);
    fireEvent.change(textarea, { target: { value: 'Line 1\nLine 2' } });

    fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true });

    expect(onSend).toHaveBeenCalledWith('Line 1\nLine 2', null);
  });

  it('renders clean baseline suggestion chips when clip is clean', () => {
    const onSend = vi.fn();
    const onUpload = vi.fn();

    render(
      <MultimodalPromptBar
        onSendMessage={onSend}
        onFileUpload={onUpload}
        diagnosticStatus="CLEAN"
        hasAnomalies={false}
      />
    );

    expect(screen.getByText('Explain Kinematic Baseline')).toBeInTheDocument();
    expect(screen.getByText('Export Verified BVH')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Explain Kinematic Baseline'));
    expect(onSend).toHaveBeenCalledWith('Explain kinematic baseline constraints and verification', null);
  });

  it('renders anomaly repair suggestion chips when anomalies are detected', () => {
    const onSend = vi.fn();
    const onUpload = vi.fn();

    render(
      <MultimodalPromptBar
        onSendMessage={onSend}
        onFileUpload={onUpload}
        hasAnomalies={true}
      />
    );

    expect(screen.getByText('Fix Foot Sliding Only')).toBeInTheDocument();
    expect(screen.getByText('Smooth Spine Jitter')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Fix Foot Sliding Only'));
    expect(onSend).toHaveBeenCalledWith('Fix foot sliding only', null);
  });

  it('handles staged file display and clearing', () => {
    const onSend = vi.fn();
    const onUpload = vi.fn();
    const onClear = vi.fn();
    const fakeFile = new File(['bvh data'], 'walk_cycle.bvh', { type: 'text/plain' });

    render(
      <MultimodalPromptBar
        onSendMessage={onSend}
        onFileUpload={onUpload}
        externalStagedFile={fakeFile}
        onClearExternalStagedFile={onClear}
      />
    );

    expect(screen.getByText('walk_cycle.bvh')).toBeInTheDocument();
    const removeBtn = screen.getByTitle('Remove staged file');
    fireEvent.click(removeBtn);
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
