import { describe, it, expect, vi } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import WhiteBoxCodeDrawer from './WhiteBoxCodeDrawer';
import RepairCompleteCard from './RepairCompleteCard';

vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }: { value: string; onChange?: (v: string) => void }) => (
    <textarea
      data-testid="mock-monaco-editor"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
}));

describe('WhiteBoxCodeDrawer', () => {
  it('does not render when isOpen is false', () => {
    render(
      <WhiteBoxCodeDrawer
        isOpen={false}
        onClose={vi.fn()}
        initialScript="import bpy; print('hello')"
      />
    );
    expect(screen.queryByTestId('white-box-code-drawer')).not.toBeInTheDocument();
  });

  it('renders drawer with initial script when isOpen is true', async () => {
    render(
      <WhiteBoxCodeDrawer
        isOpen={true}
        onClose={vi.fn()}
        initialScript="import bpy; print('repair')"
      />
    );
    expect(screen.getByTestId('white-box-code-drawer')).toBeInTheDocument();
    const editor = (await screen.findByTestId('mock-monaco-editor')) as HTMLTextAreaElement;
    expect(editor.value).toBe("import bpy; print('repair')");
  });

  it('resets code to initial script on reset button click', async () => {
    render(
      <WhiteBoxCodeDrawer
        isOpen={true}
        onClose={vi.fn()}
        initialScript="import bpy; orig = True"
      />
    );
    const editor = (await screen.findByTestId('mock-monaco-editor')) as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: 'import bpy; modified = True' } });
    expect(editor.value).toBe('import bpy; modified = True');

    fireEvent.click(screen.getByTestId('reset-script-btn'));
    expect(editor.value).toBe('import bpy; orig = True');
  });

  it('triggers onExecuteScript with edited code when run button is clicked', async () => {
    const handleExecute = vi.fn();
    render(
      <WhiteBoxCodeDrawer
        isOpen={true}
        onClose={vi.fn()}
        initialScript="import bpy; initial_call()"
        onExecuteScript={handleExecute}
      />
    );
    const editor = (await screen.findByTestId('mock-monaco-editor')) as HTMLTextAreaElement;
    fireEvent.change(editor, { target: { value: 'import bpy; custom_filter()' } });
    fireEvent.click(screen.getByTestId('run-script-btn'));

    expect(handleExecute).toHaveBeenCalledTimes(1);
    expect(handleExecute).toHaveBeenCalledWith('import bpy; custom_filter()');
  });

  it('disables run button when isExecuting is true', () => {
    const handleExecute = vi.fn();
    render(
      <WhiteBoxCodeDrawer
        isOpen={true}
        onClose={vi.fn()}
        initialScript="import bpy"
        onExecuteScript={handleExecute}
        isExecuting={true}
      />
    );
    const runBtn = screen.getByTestId('run-script-btn');
    expect(runBtn).toBeDisabled();
    fireEvent.click(runBtn);
    expect(handleExecute).not.toHaveBeenCalled();
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(
      <WhiteBoxCodeDrawer
        isOpen={true}
        onClose={handleClose}
        initialScript="import bpy"
      />
    );
    fireEvent.click(screen.getByTestId('close-drawer-btn'));
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});

describe('RepairCompleteCard', () => {
  it('renders repair completion information and handles inspect code', () => {
    const handleInspect = vi.fn();
    render(
      <RepairCompleteCard
        assetId="asset-xyz-123"
        filename="repaired_jump.bvh"
        repairedFileUrl="/bvh/asset-xyz-123"
        scriptCode="import bpy; fixed = True"
        metrics={{
          agents_executed: 3,
          qa_passed: true,
          execution_time_seconds: 0.42,
        }}
        onInspectCode={handleInspect}
      />
    );

    expect(screen.getByTestId('repair-complete-card')).toBeInTheDocument();
    expect(screen.getByText('Blender Repair Execution Complete')).toBeInTheDocument();
    expect(screen.getByText('repaired_jump.bvh')).toBeInTheDocument();
    expect(screen.getByText('0.42s')).toBeInTheDocument();
    expect(screen.getByText('3 Dynamic')).toBeInTheDocument();

    const downloadLink = screen.getByTestId('download-repaired-btn');
    expect(downloadLink).toHaveAttribute('href', 'http://localhost:8000/bvh/asset-xyz-123');
    expect(downloadLink).toHaveAttribute('download', 'repaired_jump.bvh');

    fireEvent.click(screen.getByTestId('inspect-code-btn'));
    expect(handleInspect).toHaveBeenCalledTimes(1);
    expect(handleInspect).toHaveBeenCalledWith('import bpy; fixed = True');
  });
});
