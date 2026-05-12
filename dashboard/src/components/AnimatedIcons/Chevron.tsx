import { MdChevronRight } from 'react-icons/md';

import type { JSX } from 'react';

import { cn } from '@/lib/utils';

interface ChevronRightAnimateProps {
  isExpanded?: boolean;
  animated?: boolean;
  className?: string;
}

export const ChevronRightAnimate = ({
  isExpanded,
  animated = true,
  className,
}: ChevronRightAnimateProps): JSX.Element => {
  return (
    <MdChevronRight
      className={cn(
        'transition',
        animated && "group-data-[state='open']:rotate-90",
        isExpanded && 'rotate-90',
        className,
      )}
    />
  );
};
