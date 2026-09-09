import { describe, it, expect, vi, afterEach } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import axios from 'axios';
import ConsentPromptCard from './ConsentPromptCard';

vi.mock('axios');
const mockedAxios = vi.mocked(axios, true);

describe('ConsentPromptCard', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders initial action buttons when pending consent', () => {
    render(
      <ConsentPromptCard
        analysisId="analysis-123"
        sessionId="session-123"
        findingIds={['f1', 'f2']}
      />
    );

    expect(screen.getByTestId('consent-prompt-card')).toBeInTheDocument();
    expect(screen.getByText('Plan Review & Authorization')).toBeInTheDocument();
    expect(screen.getByTestId('spawn-agents-btn')).toHaveTextContent('Spawn Agents to Fix All');
    expect(screen.getByTestId('customize-btn')).toHaveTextContent('Custom Instruction');
    expect(screen.getByTestId('decline-btn')).toHaveTextContent('Decline / Keep Original');
  });

  it('approves repair plan directly on Spawn Multi-Agents click', async () => {
    const onApproved = vi.fn();
    mockedAxios.post.mockImplementation((url) => {
      if (url.includes('/repair-plan') && !url.includes('/approve')) {
        return Promise.resolve({
          data: {
            plan_id: 'plan-xyz',
            version: 1,
            session_id: 'session-123',
          },
        });
      }
      if (url.includes('/approve')) {
        return Promise.resolve({
          data: {
            approval_id: 'appr-abc-789',
            plan_id: 'plan-xyz',
            session_id: 'session-123',
            status: 'APPROVED',
          },
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });

    render(
      <ConsentPromptCard
        analysisId="analysis-123"
        sessionId="session-123"
        findingIds={['f1', 'f2']}
        onApproved={onApproved}
      />
    );

    fireEvent.click(screen.getByTestId('spawn-agents-btn'));

    await waitFor(() => {
      expect(screen.getByText('Approved for Multi-Agent Repair')).toBeInTheDocument();
    });

    expect(screen.getByTestId('approval-id')).toHaveTextContent('appr-abc-789');
    expect(onApproved).toHaveBeenCalledWith('plan-xyz', 'appr-abc-789', undefined);
    expect(mockedAxios.post).toHaveBeenCalledWith('http://localhost:8000/analyses/analysis-123/repair-plan', {
      session_id: 'session-123',
      selected_finding_ids: ['f1', 'f2'],
    });
    expect(mockedAxios.post).toHaveBeenCalledWith('http://localhost:8000/repair-plans/plan-xyz/approve', {
      session_id: 'session-123',
      plan_id: 'plan-xyz',
      repair_plan_version: 1,
      selected_finding_ids: ['f1', 'f2'],
      confirmed: true,
    });
  });

  it('supports inline custom instruction input and approval', async () => {
    const onApproved = vi.fn();
    mockedAxios.post.mockImplementation((url) => {
      if (url.includes('/repair-plan') && !url.includes('/approve')) {
        return Promise.resolve({
          data: {
            plan_id: 'plan-custom',
            version: 1,
          },
        });
      }
      if (url.includes('/approve')) {
        return Promise.resolve({
          data: {
            approval_id: 'appr-custom-456',
          },
        });
      }
      return Promise.reject(new Error(`Unexpected url: ${url}`));
    });

    render(
      <ConsentPromptCard
        analysisId="analysis-123"
        sessionId="session-123"
        findingIds={['f1']}
        onApproved={onApproved}
      />
    );

    fireEvent.click(screen.getByTestId('customize-btn'));

    const input = screen.getByTestId('custom-instructions-input');
    expect(input).toBeInTheDocument();

    fireEvent.change(input, {
      target: { value: 'Fix left ankle only with smooth interpolation' },
    });

    fireEvent.click(screen.getByTestId('approve-custom-btn'));

    await waitFor(() => {
      expect(screen.getByText('Approved for Multi-Agent Repair')).toBeInTheDocument();
    });

    expect(screen.getByTestId('approval-id')).toHaveTextContent('appr-custom-456');
    expect(screen.getByText('Fix left ankle only with smooth interpolation')).toBeInTheDocument();
    expect(onApproved).toHaveBeenCalledWith(
      'plan-custom',
      'appr-custom-456',
      'Fix left ankle only with smooth interpolation'
    );
  });

  it('handles decline action correctly', async () => {
    const onDeclined = vi.fn();
    mockedAxios.post.mockResolvedValueOnce({ data: { status: 'CANCELLED' } });

    render(
      <ConsentPromptCard
        analysisId="analysis-123"
        sessionId="session-123"
        findingIds={['f1']}
        onDeclined={onDeclined}
      />
    );

    fireEvent.click(screen.getByTestId('decline-btn'));

    await waitFor(() => {
      expect(screen.getByText('Repair Declined')).toBeInTheDocument();
    });

    expect(onDeclined).toHaveBeenCalledTimes(1);
    expect(mockedAxios.post).toHaveBeenCalledWith('http://localhost:8000/sessions/session-123/cancel');
  });

  it('renders pre-approved card when initialApproved is true', () => {
    render(
      <ConsentPromptCard
        analysisId="analysis-123"
        sessionId="session-123"
        initialApproved={true}
        initialApprovalId="pre-appr-999"
      />
    );

    expect(screen.getByText('Approved for Multi-Agent Repair')).toBeInTheDocument();
    expect(screen.getByTestId('approval-id')).toHaveTextContent('pre-appr-999');
    expect(screen.queryByTestId('spawn-agents-btn')).not.toBeInTheDocument();
  });
});
