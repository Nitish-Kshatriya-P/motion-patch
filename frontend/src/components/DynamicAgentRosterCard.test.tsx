import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import DynamicAgentRosterCard, { type DynamicAgent } from './DynamicAgentRosterCard';

describe('DynamicAgentRosterCard', () => {
  const sampleAgents: DynamicAgent[] = [
    {
      agent_id: 'agent-1',
      role: 'LeftFoot Ground Contact & Anti-Slide Specialist',
      target_bones: ['LeftFoot', 'LeftToeBase'],
      target_frames: [30, 65],
      tools: ['query_clickhouse_rag'],
      status: 'SPAWNED',
    },
    {
      agent_id: 'agent-2',
      role: 'Spine & Torso Kinematic Smoother',
      target_bones: ['Spine'],
      target_frames: [70, 110],
      tools: ['query_clickhouse_rag'],
      status: 'THINKING',
    },
    {
      agent_id: 'agent-3',
      role: 'Hips Root Motion Stabilizer',
      target_bones: ['Hips'],
      target_frames: [0, 120],
      tools: ['query_clickhouse_rag'],
      status: 'COMPLETED',
    },
  ];

  it('renders card container and worker count badge', () => {
    render(<DynamicAgentRosterCard agents={sampleAgents} />);
    expect(screen.getByTestId('dynamic-agent-roster-card')).toBeInTheDocument();
    expect(screen.getByTestId('agent-count-badge')).toHaveTextContent('3 Workers Spawned');
    expect(screen.getByText('Dynamic Multi-Agent Roster')).toBeInTheDocument();
  });

  it('renders roles, target joints, and frame intervals for all agents', () => {
    render(<DynamicAgentRosterCard agents={sampleAgents} />);

    expect(screen.getByTestId('agent-role-agent-1')).toHaveTextContent(
      'LeftFoot Ground Contact & Anti-Slide Specialist'
    );
    expect(screen.getByTestId('agent-role-agent-2')).toHaveTextContent(
      'Spine & Torso Kinematic Smoother'
    );
    expect(screen.getByTestId('agent-role-agent-3')).toHaveTextContent(
      'Hips Root Motion Stabilizer'
    );

    expect(screen.getByTestId('agent-joint-agent-1-LeftFoot')).toHaveTextContent('LeftFoot');
    expect(screen.getByTestId('agent-joint-agent-1-LeftToeBase')).toHaveTextContent('LeftToeBase');
    expect(screen.getByTestId('agent-joint-agent-2-Spine')).toHaveTextContent('Spine');
    expect(screen.getByTestId('agent-joint-agent-3-Hips')).toHaveTextContent('Hips');

    expect(screen.getByTestId('agent-frames-agent-1')).toHaveTextContent('30 - 65');
    expect(screen.getByTestId('agent-frames-agent-2')).toHaveTextContent('70 - 110');
    expect(screen.getByTestId('agent-frames-agent-3')).toHaveTextContent('0 - 120');
  });

  it('renders status badges and spinners correctly based on agent lifecycle state', () => {
    render(<DynamicAgentRosterCard agents={sampleAgents} />);

    expect(screen.getByTestId('agent-status-agent-1')).toHaveTextContent('SPAWNED');
    expect(screen.getByTestId('status-icon-spinner-agent-1')).toBeInTheDocument();

    expect(screen.getByTestId('agent-status-agent-2')).toHaveTextContent('THINKING');
    expect(screen.getByTestId('status-icon-spinner-agent-2')).toBeInTheDocument();

    expect(screen.getByTestId('agent-status-agent-3')).toHaveTextContent('COMPLETED');
    expect(screen.getByTestId('status-icon-completed-agent-3')).toBeInTheDocument();
  });

  it('returns null when agents list is empty', () => {
    const { container } = render(<DynamicAgentRosterCard agents={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
