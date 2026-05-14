import type { JSX } from 'react';
import { FormattedMessage } from 'react-intl';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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
        <Select onValueChange={onTreeChange} value={selectedTreeName}>
          <SelectTrigger data-test-id="hardware-tree-selector">
            <SelectValue placeholder="" />
          </SelectTrigger>
          <SelectContent>
            {treeOptions.map(tree => (
              <SelectItem key={tree.value} value={tree.value}>
                {tree.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-dim-gray text-sm font-medium">
          <FormattedMessage id="hardwareListing.branchSelectorLabel" />
        </span>
        <Select onValueChange={onBranchChange} value={selectedBranchValue}>
          <SelectTrigger data-test-id="hardware-branch-selector">
            <SelectValue placeholder="" />
          </SelectTrigger>
          <SelectContent>
            {branchOptions.map(branch => (
              <SelectItem key={branch.value} value={branch.value}>
                {branch.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-dim-gray text-sm font-medium">
          <FormattedMessage id="hardwareListing.revisionSelectorLabel" />
        </span>
        <Select onValueChange={onRevisionChange} value={selectedRevisionHash}>
          <SelectTrigger data-test-id="hardware-revision-selector">
            <SelectValue placeholder="" />
          </SelectTrigger>
          <SelectContent>
            {revisionOptions.map(revision => (
              <SelectItem key={revision.value} value={revision.value}>
                {revision.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
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
