import { describe, it, expect, vi, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import KeyboardShortcutsModal from './KeyboardShortcutsModal';

describe('KeyboardShortcutsModal', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const onClose = vi.fn();
    render(<KeyboardShortcutsModal isOpen={false} onClose={onClose} />);
    expect(screen.queryByTestId('keyboard-shortcuts-modal')).not.toBeInTheDocument();
  });

  it('renders modal with hotkey categories when isOpen is true', () => {
    const onClose = vi.fn();
    render(<KeyboardShortcutsModal isOpen={true} onClose={onClose} />);
    expect(screen.getByTestId('keyboard-shortcuts-modal')).toBeInTheDocument();
    expect(screen.getByText('Keyboard Controls')).toBeInTheDocument();
    expect(screen.getByText('Playback & 3D Viewport')).toBeInTheDocument();
    expect(screen.getByText('Plan Review & Authorization Card')).toBeInTheDocument();
    expect(screen.getByText('Kinematic Diagnosis Findings')).toBeInTheDocument();
    expect(screen.getByText('Global Navigation & Studio')).toBeInTheDocument();
  });

  it('calls onClose when clicking close button or pressing Escape', () => {
    const onClose = vi.fn();
    render(<KeyboardShortcutsModal isOpen={true} onClose={onClose} />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    const closeButtons = screen.getAllByRole('button');
    fireEvent.click(closeButtons[0]);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
