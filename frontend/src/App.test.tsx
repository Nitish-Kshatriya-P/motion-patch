import { describe, it, expect, vi, beforeEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import axios from 'axios';

vi.mock('axios');
const mockedAxios = vi.mocked(axios, true);

vi.mock('./components/Viewport3D', () => ({
  default: () => <div data-testid="mock-viewport-3d">Mock Viewport</div>,
}));

describe('App mobile responsiveness', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedAxios.get.mockResolvedValue({ data: [] });
    mockedAxios.post.mockResolvedValue({ data: {} });
  });

  it('renders mobile sidebar toggle button in header', () => {
    render(<App />);
    const toggleBtn = screen.getByTestId('mobile-sidebar-toggle');
    expect(toggleBtn).toBeInTheDocument();
  });

  it('renders mobile view mode tabs when workspace is active', async () => {
    mockedAxios.get.mockImplementation((url: string) => {
      if (url.endsWith('/sessions')) {
        return Promise.resolve({
          data: [
            {
              session_id: 'sess-1',
              asset_id: 'ast-1',
              analysis_id: 'an-1',
              filename: 'test.bvh',
              duration_seconds: 2,
              frame_count: 60,
              findings_count: 0,
              status: 'CLEAN',
              created_at: '2026-09-08T10:00:00Z',
              updated_at: '2026-09-08T10:00:00Z',
            },
          ],
        });
      }
      if (url.includes('/sessions/sess-1')) {
        return Promise.resolve({
          data: {
            session_id: 'sess-1',
            asset_id: 'ast-1',
            analysis_id: 'an-1',
            filename: 'test.bvh',
            status: 'CLEAN',
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('test.bvh')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('test.bvh'));

    await waitFor(() => {
      expect(screen.getByTestId('mobile-tab-viewport')).toBeInTheDocument();
      expect(screen.getByTestId('mobile-tab-chat')).toBeInTheDocument();
      expect(screen.getByTestId('mobile-tab-split')).toBeInTheDocument();
    });

    const viewportTab = screen.getByTestId('mobile-tab-viewport');
    const chatTab = screen.getByTestId('mobile-tab-chat');
    const splitTab = screen.getByTestId('mobile-tab-split');

    fireEvent.click(chatTab);
    const mainSection = screen.getByTestId('main-inspector-container');
    expect(mainSection).toBeInTheDocument();

    fireEvent.click(splitTab);
    expect(screen.getByTestId('main-viewport-container')).toBeInTheDocument();
    expect(screen.getByTestId('main-inspector-container')).toBeInTheDocument();

    fireEvent.click(viewportTab);
    expect(screen.getByTestId('main-viewport-container')).toBeInTheDocument();
  });

  it('restores persisted chat messages when opening a session', async () => {
    mockedAxios.get.mockImplementation((url: string) => {
      if (url.endsWith('/sessions')) {
        return Promise.resolve({
          data: [
            {
              session_id: 'sess-persisted',
              asset_id: 'ast-persisted',
              analysis_id: 'an-persisted',
              filename: 'walk_clip.bvh',
              duration_seconds: 4,
              frame_count: 120,
              findings_count: 1,
              status: 'BROKEN',
              created_at: '2026-09-08T10:00:00Z',
              updated_at: '2026-09-08T10:00:00Z',
            },
          ],
        });
      }
      if (url.includes('/sessions/sess-persisted/messages')) {
        return Promise.resolve({
          data: {
            messages: [
              {
                id: 'msg-custom-1',
                sender: 'user',
                timestamp: '2026-09-08T10:01:00Z',
                text: 'Please inspect the motion trajectory',
                sessionId: 'sess-persisted',
              },
              {
                id: 'msg-custom-2',
                sender: 'assistant',
                timestamp: '2026-09-08T10:01:05Z',
                text: 'Formulated safe Laplacian smoothing filter.',
                sessionId: 'sess-persisted',
              },
            ],
          },
        });
      }
      if (url.includes('/analyses/an-persisted/summary')) {
        return Promise.resolve({
          data: {
            analysis_id: 'an-persisted',
            status: 'BROKEN',
            summary: 'Detected root jitter',
            findings: [],
            broken_joints: ['Hips'],
            frame_count: 120,
            fps: 30,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText('walk_clip.bvh')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('walk_clip.bvh'));

    await waitFor(() => {
      expect(screen.getByTestId('mobile-tab-chat')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('mobile-tab-chat'));

    await waitFor(() => {
      expect(screen.getByText('Please inspect the motion trajectory')).toBeInTheDocument();
      expect(screen.getByText('Formulated safe Laplacian smoothing filter.')).toBeInTheDocument();
    });
  });
});

