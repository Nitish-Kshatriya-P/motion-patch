import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import HomepageThreadHistory from './HomepageThreadHistory';
import type { SessionSummary } from './SessionSidebar';

describe('HomepageThreadHistory', () => {
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
    {
      session_id: 's-3',
      asset_id: 'a-3',
      analysis_id: 'an-3',
      lifecycle_state: 'ANALYZED',
      created_at: '2026-09-07T08:00:00Z',
      updated_at: '2026-09-07T08:00:00Z',
      filename: '08c17b6c-31ac-4074-99a9-134745582312.bvh',
      title: 'RightFoot Foot Sliding',
      duration_seconds: 2.1,
      frame_count: 63,
      findings_count: 2,
      status: 'NEEDS_REVIEW',
    },
  ];

  it('renders human-friendly titles and metadata badges', () => {
    render(
      <HomepageThreadHistory
        sessions={mockSessions}
        onSelectSession={vi.fn()}
      />
    );

    expect(screen.getByText('LeftLeg Rotation Jitter')).toBeInTheDocument();
    expect(screen.getByText('hero_walk_sample.bvh')).toBeInTheDocument();
    expect(screen.getByText('RightFoot Foot Sliding')).toBeInTheDocument();
    expect(screen.getByText('Clean')).toBeInTheDocument();
    expect(screen.getByText('1 Fault')).toBeInTheDocument();
    expect(screen.getByText('2 Faults')).toBeInTheDocument();
  });

  it('filters sessions by search term', () => {
    render(
      <HomepageThreadHistory
        sessions={mockSessions}
        onSelectSession={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText('Search history...');
    fireEvent.change(searchInput, { target: { value: 'hero' } });

    expect(screen.getByText('hero_walk_sample.bvh')).toBeInTheDocument();
    expect(screen.queryByText('LeftLeg Rotation Jitter')).not.toBeInTheDocument();
    expect(screen.queryByText('RightFoot Foot Sliding')).not.toBeInTheDocument();
  });

  it('filters sessions by status tabs', () => {
    render(
      <HomepageThreadHistory
        sessions={mockSessions}
        onSelectSession={vi.fn()}
      />
    );

    fireEvent.click(screen.getByText(/Faults \(2\)/));
    expect(screen.getByText('LeftLeg Rotation Jitter')).toBeInTheDocument();
    expect(screen.getByText('RightFoot Foot Sliding')).toBeInTheDocument();
    expect(screen.queryByText('hero_walk_sample.bvh')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText(/Clean \(1\)/));
    expect(screen.getByText('hero_walk_sample.bvh')).toBeInTheDocument();
    expect(screen.queryByText('LeftLeg Rotation Jitter')).not.toBeInTheDocument();
  });

  it('invokes onSelectSession when a thread card is clicked', () => {
    const handleSelect = vi.fn();
    render(
      <HomepageThreadHistory
        sessions={mockSessions}
        onSelectSession={handleSelect}
      />
    );

    fireEvent.click(screen.getByText('hero_walk_sample.bvh'));
    expect(handleSelect).toHaveBeenCalledWith(mockSessions[1]);
  });

  it('shows empty message when search yields no matches', () => {
    render(
      <HomepageThreadHistory
        sessions={mockSessions}
        onSelectSession={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText('Search history...');
    fireEvent.change(searchInput, { target: { value: 'nonexistent_query_xyz' } });

    expect(screen.getByText('No threads match your current filter or search criteria.')).toBeInTheDocument();
  });
});
