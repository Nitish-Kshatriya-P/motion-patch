import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RepairCompleteCard from './RepairCompleteCard';

describe('RepairCompleteCard', () => {
  it('renders repair complete card and ready badge', () => {
    render(
      <RepairCompleteCard
        assetId="asset-12345678"
        filename="repaired_01_WalkFwd_Loop_RightContact.bvh"
        repairedFileUrl="/bvh/asset-12345678"
        scriptCode="import bpy"
      />
    );

    const card = screen.getByTestId('repair-complete-card');
    expect(card).toBeInTheDocument();
    expect(card).toHaveClass('overflow-hidden');

    const badge = screen.getByText('Ready for 3D Viewport');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('whitespace-nowrap');
    expect(badge).toHaveClass('shrink-0');
  });

  it('triggers onInspectCode with script code on inspect click', () => {
    const handleInspect = vi.fn();
    render(
      <RepairCompleteCard
        assetId="asset-12345678"
        repairedFileUrl="/bvh/asset-12345678"
        scriptCode="import bpy; print('inspect')"
        onInspectCode={handleInspect}
      />
    );

    fireEvent.click(screen.getByTestId('inspect-code-btn'));
    expect(handleInspect).toHaveBeenCalledWith("import bpy; print('inspect')");
  });
});
