import { describe, it, expect } from 'vitest';
import '@testing-library/jest-dom/vitest';
import { render } from '@testing-library/react';
import MotionPatchLogo, { type LogoVariant } from './MotionPatchLogo';

describe('MotionPatchLogo', () => {
  it('renders SVG with default props and accessibility label', () => {
    const { container } = render(<MotionPatchLogo />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
    expect(svg).toHaveAttribute('aria-label', 'MotionPatch Symbol');
    expect(svg).toHaveAttribute('width', '18');
    expect(svg).toHaveAttribute('height', '18');
  });

  it('renders correct dimensions for size variants', () => {
    const { container: containerSm } = render(<MotionPatchLogo size="sm" />);
    expect(containerSm.querySelector('svg')).toHaveAttribute('width', '14');

    const { container: containerLg } = render(<MotionPatchLogo size="lg" />);
    expect(containerLg.querySelector('svg')).toHaveAttribute('width', '24');

    const { container: containerXl } = render(<MotionPatchLogo size="xl" />);
    expect(containerXl.querySelector('svg')).toHaveAttribute('width', '28');

    const { container: containerNum } = render(<MotionPatchLogo size={32} />);
    expect(containerNum.querySelector('svg')).toHaveAttribute('width', '32');
  });

  it('applies custom className and accent prop', () => {
    const { container } = render(<MotionPatchLogo className="text-blue-500" showAccent={false} />);
    const svg = container.querySelector('svg');
    expect(svg).toHaveClass('text-blue-500');
  });

  it('renders all 5 logo variants without error', () => {
    const variants: LogoVariant[] = ['hexacore', 'apex', 'tangent', 'ribbon', 'suture'];
    for (const v of variants) {
      const { container } = render(<MotionPatchLogo variant={v} />);
      const svg = container.querySelector('svg');
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveAttribute('aria-label', 'MotionPatch Symbol');
      expect(svg?.children.length).toBeGreaterThan(0);
    }
  });
});
