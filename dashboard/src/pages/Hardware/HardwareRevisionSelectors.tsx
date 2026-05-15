import { useEffect, useMemo, useRef, useState, type JSX } from 'react';
import { FormattedMessage } from 'react-intl';
import { Check, ChevronsUpDown } from 'lucide-react';
import { useVirtualizer } from '@tanstack/react-virtual';

import { Button } from '@/components/ui/button';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import type {
  HardwareRevisionSelection,
  HardwareSelectorBranch,
  HardwareSelectorTree,
} from '@/types/hardware';

import { encodeBranchValue } from './hardwareSelection';

const SHORT_HASH_LENGTH = 12;

type SelectorOption = {
  value: string;
  label: string;
};

const shortHash = (value: string): string => value.slice(0, SHORT_HASH_LENGTH);

interface HardwareRevisionSelectorsPresentationProps {
  treeOptions: SelectorOption[];
  branchOptions: SelectorOption[];
  revisionOptions: SelectorOption[];
  selectedTreeName?: string;
  selectedBranchValue?: string;
  selectedRevisionHash?: string;
  onTreeChange: (nextTreeName: string) => void;
  onBranchChange: (nextBranchValue: string) => void;
  onRevisionChange: (nextRevisionHash: string) => void;
}

interface HardwareRevisionComboboxProps {
  options: SelectorOption[];
  selectedValue?: string;
  onValueChange: (nextValue: string) => void;
  placeholder: string;
  searchPlaceholder: string;
  emptyMessage: string;
  dataTestId: string;
  disabled?: boolean;
  virtualized?: boolean;
  listHeight?: string;
  virtualItemSize?: number;
}

const HardwareRevisionCombobox = ({
  options,
  selectedValue,
  onValueChange,
  placeholder,
  searchPlaceholder,
  emptyMessage,
  dataTestId,
  disabled = false,
  virtualized = false,
  listHeight = '300px',
  virtualItemSize = 36,
}: HardwareRevisionComboboxProps): JSX.Element => {
  const [open, setOpen] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const listRef = useRef<HTMLDivElement | null>(null);
  const selectedOption = options.find(option => option.value === selectedValue);
  const filteredOptions = useMemo(() => {
    const normalizedSearch = searchValue.trim().toLowerCase();
    if (normalizedSearch.length === 0) {
      return options;
    }

    return options.filter(option => {
      const optionLabel = option.label.toLowerCase();
      const optionValue = option.value.toLowerCase();

      return (
        optionLabel.includes(normalizedSearch) ||
        optionValue.includes(normalizedSearch)
      );
    });
  }, [options, searchValue]);
  const selectedIndexInFiltered = useMemo(
    () => filteredOptions.findIndex(option => option.value === selectedValue),
    [filteredOptions, selectedValue],
  );
  const rowVirtualizer = useVirtualizer({
    count: filteredOptions.length,
    getScrollElement: () => listRef.current,
    estimateSize: () => virtualItemSize,
    overscan: 8,
    enabled: virtualized && open,
    initialRect: {
      width: 220,
      height: 300,
    },
  });

  const handleSelect = (nextValue: string): void => {
    onValueChange(nextValue);
    setOpen(false);
  };

  useEffect(() => {
    if (!virtualized || !open || selectedIndexInFiltered < 0) {
      return;
    }

    requestAnimationFrame(() => {
      rowVirtualizer.scrollToIndex(selectedIndexInFiltered, { align: 'auto' });
    });
  }, [open, rowVirtualizer, selectedIndexInFiltered, virtualized]);

  return (
    <Popover
      onOpenChange={nextOpen => {
        setOpen(nextOpen);
        if (!nextOpen) {
          setSearchValue('');
        }
      }}
      open={open}
    >
      <PopoverTrigger asChild>
        <Button
          aria-expanded={open}
          className={cn(
            'w-[220px] justify-between',
            !selectedOption && 'text-slate-500',
          )}
          data-test-id={dataTestId}
          disabled={disabled}
          role="combobox"
          variant="outline"
        >
          <span className="truncate">
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[220px] p-0">
        <Command shouldFilter={!virtualized}>
          <CommandInput
            onValueChange={virtualized ? setSearchValue : undefined}
            placeholder={searchPlaceholder}
            value={virtualized ? searchValue : undefined}
          />
          {virtualized ? (
            <CommandList
              className="max-h-none"
              ref={listRef}
              style={{ height: listHeight }}
            >
              {filteredOptions.length === 0 ? (
                <CommandEmpty>{emptyMessage}</CommandEmpty>
              ) : (
                <div
                  className="relative p-1"
                  style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
                >
                  {rowVirtualizer.getVirtualItems().map(virtualItem => {
                    const option = filteredOptions[virtualItem.index];

                    return (
                      <CommandItem
                        className="absolute top-0 left-0 w-full"
                        key={option.value}
                        keywords={[option.label, option.value]}
                        onSelect={() => {
                          handleSelect(option.value);
                        }}
                        style={{
                          height: `${virtualItem.size}px`,
                          transform: `translateY(${virtualItem.start}px)`,
                        }}
                        value={option.value}
                      >
                        <span className="truncate">{option.label}</span>
                        <Check
                          className={cn(
                            'ml-auto h-4 w-4 shrink-0',
                            selectedValue === option.value
                              ? 'opacity-100'
                              : 'opacity-0',
                          )}
                        />
                      </CommandItem>
                    );
                  })}
                </div>
              )}
            </CommandList>
          ) : (
            <CommandList>
              <CommandEmpty>{emptyMessage}</CommandEmpty>
              <CommandGroup>
                {options.map(option => (
                  <CommandItem
                    key={option.value}
                    keywords={[option.label]}
                    onSelect={() => {
                      handleSelect(option.value);
                    }}
                    value={option.value}
                  >
                    <span className="truncate">{option.label}</span>
                    <Check
                      className={cn(
                        'ml-auto h-4 w-4 shrink-0',
                        selectedValue === option.value
                          ? 'opacity-100'
                          : 'opacity-0',
                      )}
                    />
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          )}
        </Command>
      </PopoverContent>
    </Popover>
  );
};

const HardwareRevisionSelectorsPresentation = ({
  treeOptions,
  branchOptions,
  revisionOptions,
  selectedTreeName,
  selectedBranchValue,
  selectedRevisionHash,
  onTreeChange,
  onBranchChange,
  onRevisionChange,
}: HardwareRevisionSelectorsPresentationProps): JSX.Element => {
  return (
    <div className="flex flex-wrap items-center gap-4">
      <div className="flex items-center gap-2">
        <span className="text-dim-gray text-sm font-medium">
          <FormattedMessage id="hardwareListing.treeSelectorLabel" />
        </span>
        <HardwareRevisionCombobox
          dataTestId="hardware-tree-selector"
          emptyMessage="No tree found."
          onValueChange={onTreeChange}
          options={treeOptions}
          placeholder="Select tree"
          searchPlaceholder="Search tree..."
          selectedValue={selectedTreeName}
        />
      </div>

      <div className="flex items-center gap-2">
        <span className="text-dim-gray text-sm font-medium">
          <FormattedMessage id="hardwareListing.branchSelectorLabel" />
        </span>
        <HardwareRevisionCombobox
          dataTestId="hardware-branch-selector"
          disabled={branchOptions.length === 0}
          emptyMessage="No branch found."
          onValueChange={onBranchChange}
          options={branchOptions}
          placeholder="Select branch"
          searchPlaceholder="Search branch..."
          selectedValue={selectedBranchValue}
        />
      </div>

      <div className="flex items-center gap-2">
        <span className="text-dim-gray text-sm font-medium">
          <FormattedMessage id="hardwareListing.revisionSelectorLabel" />
        </span>
        <HardwareRevisionCombobox
          dataTestId="hardware-revision-selector"
          disabled={revisionOptions.length === 0}
          emptyMessage="No revision found."
          listHeight="300px"
          onValueChange={onRevisionChange}
          options={revisionOptions}
          placeholder="Select revision"
          searchPlaceholder="Search revision..."
          selectedValue={selectedRevisionHash}
          virtualized
        />
      </div>
    </div>
  );
};

interface HardwareRevisionSelectorsProps {
  selectors: HardwareSelectorTree[];
  selectedTree: HardwareSelectorTree | null;
  selectedBranch: HardwareSelectorBranch | null;
  selection: HardwareRevisionSelection | null;
  onTreeChange: (nextTreeName: string) => void;
  onBranchChange: (nextBranchValue: string) => void;
  onRevisionChange: (nextRevisionHash: string) => void;
}

export const HardwareRevisionSelectors = ({
  selectors,
  selectedTree,
  selectedBranch,
  selection,
  onTreeChange,
  onBranchChange,
  onRevisionChange,
}: HardwareRevisionSelectorsProps): JSX.Element => {
  const treeOptions: SelectorOption[] = selectors.map(tree => ({
    value: tree.tree_name,
    label: tree.tree_name,
  }));

  const branchOptions: SelectorOption[] = (selectedTree?.branches ?? []).map(
    branch => ({
      value: encodeBranchValue(
        branch.git_repository_url,
        branch.git_repository_branch,
      ),
      label: branch.git_repository_branch,
    }),
  );

  const revisionOptions: SelectorOption[] = (
    selectedBranch?.revisions ?? []
  ).map(revision => ({
    value: revision.git_commit_hash,
    label: revision.git_commit_name ?? shortHash(revision.git_commit_hash),
  }));

  const selectedBranchValue = selection
    ? encodeBranchValue(selection.gitRepositoryUrl, selection.gitBranch)
    : undefined;

  return (
    <HardwareRevisionSelectorsPresentation
      treeOptions={treeOptions}
      branchOptions={branchOptions}
      revisionOptions={revisionOptions}
      selectedTreeName={selection?.treeName}
      selectedBranchValue={selectedBranchValue}
      selectedRevisionHash={selection?.gitCommitHash}
      onTreeChange={onTreeChange}
      onBranchChange={onBranchChange}
      onRevisionChange={onRevisionChange}
    />
  );
};
