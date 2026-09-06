import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ChatStream, { type ChatMessage } from './ChatStream';

describe('ChatStream', () => {
  it('renders empty state when there are no messages', () => {
    render(<ChatStream messages={[]} />);

    expect(screen.getByText('Codex Kinematic Inspector')).toBeInTheDocument();
    expect(screen.getByText('Drop BVH file or type instruction')).toBeInTheDocument();
  });

  it('renders user message in a card and assistant message without a card, without You or MotionPatch Agent text', () => {
    const mockMessages: ChatMessage[] = [
      {
        id: 'msg-1',
        sender: 'user',
        timestamp: '2026-09-06T12:00:00.000Z',
        text: 'Please check LeftFoot at frame 42 for foot sliding',
      },
      {
        id: 'msg-2',
        sender: 'assistant',
        timestamp: '2026-09-06T12:00:05.000Z',
        text: 'Inspected LeftFoot and confirmed anomaly at frames 42-50.',
      },
    ];

    render(<ChatStream messages={mockMessages} activeSessionId="session-abc12345" />);

    expect(screen.getByTestId('chat-turn-msg-1')).toBeInTheDocument();
    expect(screen.getByTestId('chat-turn-msg-2')).toBeInTheDocument();
    expect(screen.queryByText('You')).not.toBeInTheDocument();
    expect(screen.queryByText('MotionPatch Agent')).not.toBeInTheDocument();
    expect(screen.getByText('#session-')).toBeInTheDocument();

    const userMsg = screen.getByTestId('user-message-msg-1');
    const assistantMsg = screen.getByTestId('assistant-message-msg-2');
    expect(userMsg).toHaveClass('rounded-xl');
    expect(assistantMsg).not.toHaveClass('rounded-xl');
  });

  it('renders joint and frame interactive tokens with click handlers', () => {
    const onSelectFinding = vi.fn();
    const mockMessages: ChatMessage[] = [
      {
        id: 'msg-1',
        sender: 'assistant',
        timestamp: '2026-09-06T12:00:00.000Z',
        text: 'Observed RightFoot slipping at frames 14-20.',
      },
    ];

    render(<ChatStream messages={mockMessages} onSelectFinding={onSelectFinding} />);

    const jointBtn = screen.getByRole('button', { name: 'RightFoot' });
    expect(jointBtn).toBeInTheDocument();
    fireEvent.click(jointBtn);
    expect(onSelectFinding).toHaveBeenCalledWith('', 0, 'RightFoot');

    const frameBtn = screen.getByRole('button', { name: 'frames 14-20' });
    expect(frameBtn).toBeInTheDocument();
    fireEvent.click(frameBtn);
    expect(onSelectFinding).toHaveBeenCalledWith('', 14);
  });

  it('renders proposed plan authorization card when plan data is present', () => {
    const onAuthorize = vi.fn();
    const mockMessages: ChatMessage[] = [
      {
        id: 'msg-1',
        sender: 'assistant',
        timestamp: '2026-09-06T12:00:00.000Z',
        text: 'I recommend smoothing the spine.',
        proposedPlan: {
          session_id: 'sess-1',
          description: 'Smooth spine jitter across frames 10-30',
          selected_joints: ['Spine'],
        },
      },
    ];

    render(<ChatStream messages={mockMessages} onAuthorizeProposedPlan={onAuthorize} />);

    expect(screen.getByText('Proposed Targeted Repair Plan')).toBeInTheDocument();
    expect(screen.getByText('Smooth spine jitter across frames 10-30')).toBeInTheDocument();
    const authBtn = screen.getByRole('button', { name: /Authorize Agents/i });
    fireEvent.click(authBtn);
    expect(onAuthorize).toHaveBeenCalledWith('msg-1', mockMessages[0].proposedPlan);
  });

  it('renders answer generating indicator when isGenerating is true', () => {
    const mockMessages: ChatMessage[] = [
      {
        id: 'msg-1',
        sender: 'user',
        timestamp: '2026-09-06T12:00:00.000Z',
        text: 'How do I fix foot sliding?',
      },
    ];

    render(<ChatStream messages={mockMessages} isGenerating={true} />);

    expect(screen.getByTestId('generating-indicator')).toBeInTheDocument();
    expect(screen.getByText('Generating answer...')).toBeInTheDocument();
    expect(screen.getByText('Thinking...')).toBeInTheDocument();
  });

  it('does not render answer generating indicator when isGenerating is false', () => {
    const mockMessages: ChatMessage[] = [
      {
        id: 'msg-1',
        sender: 'user',
        timestamp: '2026-09-06T12:00:00.000Z',
        text: 'How do I fix foot sliding?',
      },
    ];

    render(<ChatStream messages={mockMessages} isGenerating={false} />);

    expect(screen.queryByTestId('generating-indicator')).not.toBeInTheDocument();
    expect(screen.queryByText('Generating answer...')).not.toBeInTheDocument();
  });
});
