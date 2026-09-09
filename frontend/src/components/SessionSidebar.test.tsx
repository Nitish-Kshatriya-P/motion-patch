import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SessionSidebar, {
  isUuidLike,
  formatSessionTitle,
  type SessionSummary,
} from './SessionSidebar';

describe('isUuidLike helper', () => {
  it('detects standard hyphenated UUIDs with or without extensions', () => {
    expect(isUuidLike('092cb236-75a4-481a-bba9-7281ca418847')).toBe(true);
    expect(isUuidLike('092cb236-75a4-481a-bba9-7281ca418847.bvh')).toBe(true);
    expect(isUuidLike('08c17b6c-31ac-4074-99a9-134745582312.bvh')).toBe(true);
  });

  it('detects long hex strings', () => {
    expect(isUuidLike('092cb23675a4481abba97281ca418847')).toBe(true);
    expect(isUuidLike('092cb23675a4481abba97281ca418847.bvh')).toBe(true);
  });

  it('rejects human-readable filenames and empty values', () => {
    expect(isUuidLike('hero_walk_sample.bvh')).toBe(false);
    expect(isUuidLike('19_03.bvh')).toBe(false);
    expect(isUuidLike('test.bvh')).toBe(false);
    expect(isUuidLike('')).toBe(false);
    expect(isUuidLike(null)).toBe(false);
    expect(isUuidLike(undefined)).toBe(false);
  });
});

describe('formatSessionTitle helper', () => {
  const baseSession: SessionSummary = {
    session_id: 'session-123',
    asset_id: 'asset-123',
    analysis_id: 'analysis-123',
    lifecycle_state: 'ANALYZED',
    created_at: '2026-09-07T10:00:00Z',
    updated_at: '2026-09-07T10:00:00Z',
    filename: 'hero_walk_sample.bvh',
    duration_seconds: 3.5,
    frame_count: 105,
    findings_count: 0,
    status: 'CLEAN',
  };

  it('returns human-readable filename directly', () => {
    expect(formatSessionTitle(baseSession)).toBe('hero_walk_sample.bvh');
  });

  it('prefers non-uuid title if already present on session', () => {
    const session: SessionSummary = {
      ...baseSession,
      filename: '092cb236-75a4-481a-bba9-7281ca418847.bvh',
      title: 'Custom Hero Walk Animation',
    };
    expect(formatSessionTitle(session)).toBe('Custom Hero Walk Animation');
  });

  it('derives descriptive fault title from diagnostic summary for UUID files', () => {
    const session: SessionSummary = {
      ...baseSession,
      filename: '092cb236-75a4-481a-bba9-7281ca418847.bvh',
      status: 'NEEDS_REVIEW',
      findings_count: 1,
      diagnostic_summary: 'Anomalies detected: - LeftLeg: frames 12-45 (rotation_jitter, confidence: 0.95)',
    };
    expect(formatSessionTitle(session)).toBe('LeftLeg Rotation Jitter');
  });

  it('falls back to findings count if diagnostic summary pattern does not match', () => {
    const session: SessionSummary = {
      ...baseSession,
      filename: '092cb236-75a4-481a-bba9-7281ca418847.bvh',
      status: 'NEEDS_REVIEW',
      findings_count: 3,
      diagnostic_summary: null,
    };
    expect(formatSessionTitle(session)).toBe('3 Kinematic Faults');
  });

  it('formats clean take with frame count for UUID files', () => {
    const session: SessionSummary = {
      ...baseSession,
      filename: '09bf1742-349c-43f4-af01-be2772591a2b.bvh',
      status: 'CLEAN',
      findings_count: 0,
      frame_count: 120,
    };
    expect(formatSessionTitle(session)).toBe('Clean Take (120f)');
  });

  it('formats inconclusive take with frame count for UUID files', () => {
    const session: SessionSummary = {
      ...baseSession,
      filename: '09432fae-4770-4165-8bc2-52a237119283.bvh',
      status: 'INCONCLUSIVE',
      findings_count: 0,
      frame_count: 24,
    };
    expect(formatSessionTitle(session)).toBe('Inconclusive Scan (24f)');
  });
});

describe('SessionSidebar component', () => {
  const mockSessions: SessionSummary[] = [
    {
      session_id: 's-1',
      asset_id: 'a-1',
      analysis_id: 'an-1',
      lifecycle_state: 'ANALYZED',
      created_at: '2026-09-07T10:00:00Z',
      updated_at: '2026-09-07T10:00:00Z',
      filename: '092cb236-75a4-481a-bba9-7281ca418847.bvh',
      title: 'LeftLeg Rotation Jitter',
      duration_seconds: 4.2,
      frame_count: 126,
      findings_count: 1,
      status: 'NEEDS_REVIEW',
    },
    {
      session_id: 's-2',
      asset_id: 'a-2',
      analysis_id: 'an-2',
      lifecycle_state: 'ANALYZED',
      created_at: '2026-09-07T09:30:00Z',
      updated_at: '2026-09-07T09:30:00Z',
      filename: 'hero_walk_sample.bvh',
      duration_seconds: 5.0,
      frame_count: 150,
      findings_count: 0,
      status: 'CLEAN',
    },
  ];

  it('renders human-friendly titles instead of raw UUIDs in thread list', () => {
    render(
      <SessionSidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        isOpen={true}
        onToggleOpen={vi.fn()}
      />
    );

    expect(screen.getByText('LeftLeg Rotation Jitter')).toBeInTheDocument();
    expect(screen.getByText('hero_walk_sample.bvh')).toBeInTheDocument();
    expect(screen.queryByText('092cb236-75a4-481a-bba9-7281ca418847.bvh')).not.toBeInTheDocument();
  });

  it('filters threads by title or filename when searching', () => {
    render(
      <SessionSidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        isOpen={true}
        onToggleOpen={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText('Search threads...');
    fireEvent.change(searchInput, { target: { value: 'jitter' } });

    expect(screen.getByText('LeftLeg Rotation Jitter')).toBeInTheDocument();
    expect(screen.queryByText('hero_walk_sample.bvh')).not.toBeInTheDocument();

    fireEvent.change(searchInput, { target: { value: '092cb236' } });
    expect(screen.getByText('LeftLeg Rotation Jitter')).toBeInTheDocument();
  });

  it('calls onSelectSession when a thread button is clicked', () => {
    const handleSelect = vi.fn();
    render(
      <SessionSidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        onSelectSession={handleSelect}
        onNewSession={vi.fn()}
        isOpen={true}
        onToggleOpen={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText('hero_walk_sample.bvh'));
    expect(handleSelect).toHaveBeenCalledWith(mockSessions[1]);
  });

  it('renders collapsed state with toggle button', () => {
    const handleToggle = vi.fn();
    render(
      <SessionSidebar
        sessions={mockSessions}
        activeSessionId="s-1"
        onSelectSession={vi.fn()}
        onNewSession={vi.fn()}
        isOpen={false}
        onToggleOpen={handleToggle}
      />
    );

    const expandBtn = screen.getByTitle('Expand sidebar (Cmd+B)');
    expect(expandBtn).toBeInTheDocument();
    fireEvent.click(expandBtn);
    expect(handleToggle).toHaveBeenCalledTimes(1);
  });
});
