import React from 'react';

export type LogoVariant = 'hexacore' | 'apex' | 'tangent' | 'ribbon' | 'suture';

export interface MotionPatchLogoProps extends React.SVGProps<SVGSVGElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl' | number;
  className?: string;
  showAccent?: boolean;
  variant?: LogoVariant;
}

export const MotionPatchLogo: React.FC<MotionPatchLogoProps> = ({
  size = 'md',
  className = '',
  showAccent = true,
  variant = 'suture',
  ...props
}) => {
  const pixelSize = typeof size === 'number'
    ? size
    : size === 'sm'
      ? 14
      : size === 'md'
        ? 18
        : size === 'lg'
          ? 24
          : 28;

  const renderContent = () => {
    switch (variant) {
      case 'apex':
        return (
          <>
            <path
              d="M12 2.8L21.2 19.5H16.2L12 11.2L7.8 19.5H2.8L12 2.8Z"
              fill="currentColor"
              fillRule="evenodd"
              clipRule="evenodd"
            />
            <path
              d="M8.2 14.8H15.8"
              stroke={showAccent ? '#38bdf8' : 'currentColor'}
              strokeWidth={2}
              strokeLinecap="round"
            />
            <circle
              cx={12}
              cy={14.8}
              r={1.5}
              fill={showAccent ? '#10b981' : 'currentColor'}
            />
          </>
        );
      case 'tangent':
        return (
          <>
            <path
              d="M3.5 15.5C4.2 8.5 7.8 4 14.8 4C18.2 4 20.5 5.8 20.5 8.5C20.5 11.2 18 12.8 14.8 12.8H12"
              stroke="currentColor"
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M20.5 8.5C19.8 15.5 16.2 20 9.2 20C5.8 20 3.5 18.2 3.5 15.5C3.5 12.8 6 11.2 9.2 11.2H12"
              stroke={showAccent ? '#38bdf8' : 'currentColor'}
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {showAccent && (
              <circle
                cx={12}
                cy={12}
                r={1.6}
                fill="#10b981"
                stroke="none"
              />
            )}
          </>
        );
      case 'ribbon':
        return (
          <>
            <path
              d="M4 19V5.5L10.5 14L14.5 9H17.8C19.5 9 20.8 10.3 20.8 12C20.8 13.7 19.5 15 17.8 15H14.5V19"
              stroke="currentColor"
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {showAccent && (
              <>
                <line
                  x1={10.5}
                  y1={14}
                  x2={14.5}
                  y2={9}
                  stroke="#38bdf8"
                  strokeWidth={2.5}
                  strokeLinecap="round"
                />
                <circle cx={17.8} cy={12} r={1.5} fill="#10b981" />
              </>
            )}
          </>
        );
      case 'hexacore':
        return (
          <>
            <path
              d="M12 3.2L18.8 7.1L12 11L5.2 7.1L12 3.2Z"
              fill="currentColor"
            />
            <path
              d="M4.4 8.6L11.2 12.5V20.4L4.4 16.5V8.6Z"
              fill="currentColor"
              fillOpacity={0.65}
            />
            <path
              d="M19.6 8.6L12.8 12.5V20.4L19.6 16.5V8.6Z"
              fill={showAccent ? '#38bdf8' : 'currentColor'}
              fillOpacity={showAccent ? 1 : 0.4}
            />
            {showAccent && (
              <circle cx={12} cy={12.5} r={1.4} fill="#10b981" />
            )}
          </>
        );
      case 'suture':
      default:
        return (
          <>
            <path
              d="M7.5 8C4.5 8 3 10 3 12C3 14 4.5 16 7.5 16C10.8 16 11.8 12 12 12C12.2 12 13.2 16 16.5 16C19.5 16 21 14 21 12C21 10 19.5 8 16.5 8C13.2 8 12.2 12 12 12C11.8 12 10.8 8 7.5 8Z"
              stroke="currentColor"
              strokeWidth={2.2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <line
              x1={9}
              y1={12}
              x2={15}
              y2={12}
              stroke={showAccent ? '#38bdf8' : 'currentColor'}
              strokeWidth={2.2}
              strokeLinecap="round"
            />
            <circle
              cx={12}
              cy={12}
              r={1.5}
              fill={showAccent ? '#10b981' : 'currentColor'}
            />
          </>
        );
    }
  };

  return (
    <svg
      viewBox="0 0 24 24"
      width={pixelSize}
      height={pixelSize}
      fill="none"
      className={className}
      aria-label="MotionPatch Symbol"
      {...props}
    >
      {renderContent()}
    </svg>
  );
};

export default MotionPatchLogo;
