import type {
  HardwareRevisionSelection,
  HardwareSelectorBranch,
  HardwareSelectorRevision,
  HardwareSelectorTree,
} from '@/types/hardware';

type ResolvedHardwareSelection = {
  selection: HardwareRevisionSelection | null;
  revisionStartTime: string | null;
  wasReset: boolean;
};

const BRANCH_VALUE_SEPARATOR = '::';

const getTimestamp = (timestamp: string): number => {
  return new Date(timestamp).getTime();
};

const getLatestRevision = (
  revisions: HardwareSelectorRevision[],
): HardwareSelectorRevision | null => {
  return (
    revisions.reduce<HardwareSelectorRevision | null>((latest, revision) => {
      if (latest === null) {
        return revision;
      }

      return getTimestamp(revision.start_time) > getTimestamp(latest.start_time)
        ? revision
        : latest;
    }, null) ?? null
  );
};

const getLatestBranch = (
  branches: HardwareSelectorBranch[],
): HardwareSelectorBranch | null => {
  return (
    branches.reduce<HardwareSelectorBranch | null>((latest, branch) => {
      if (latest === null) {
        return branch;
      }

      return getTimestamp(branch.latest_start_time) >
        getTimestamp(latest.latest_start_time)
        ? branch
        : latest;
    }, null) ?? null
  );
};

export const encodeBranchValue = (
  gitRepositoryUrl: string,
  gitBranch: string,
): string => {
  return `${encodeURIComponent(gitRepositoryUrl)}${BRANCH_VALUE_SEPARATOR}${encodeURIComponent(gitBranch)}`;
};

export const decodeBranchValue = (
  branchValue: string,
): { gitRepositoryUrl: string; gitBranch: string } | null => {
  const [encodedGitRepositoryUrl, encodedGitBranch] = branchValue.split(
    BRANCH_VALUE_SEPARATOR,
  );

  if (!encodedGitRepositoryUrl || !encodedGitBranch) {
    return null;
  }

  return {
    gitRepositoryUrl: decodeURIComponent(encodedGitRepositoryUrl),
    gitBranch: decodeURIComponent(encodedGitBranch),
  };
};

export const getGlobalLatestHardwareSelection = (
  trees: HardwareSelectorTree[],
): {
  selection: HardwareRevisionSelection;
  revisionStartTime: string;
} | null => {
  return (
    trees.reduce<{
      selection: HardwareRevisionSelection;
      revisionStartTime: string;
    } | null>((latest, tree) => {
      const latestBranch = getLatestBranch(tree.branches);
      if (latestBranch === null) {
        return latest;
      }

      const latestRevision = getLatestRevision(latestBranch.revisions);
      if (latestRevision === null) {
        return latest;
      }

      const nextSelection = {
        selection: {
          treeName: tree.tree_name,
          gitRepositoryUrl: latestBranch.git_repository_url,
          gitBranch: latestBranch.git_repository_branch,
          gitCommitHash: latestRevision.git_commit_hash,
        },
        revisionStartTime: latestRevision.start_time,
      };

      if (latest === null) {
        return nextSelection;
      }

      return getTimestamp(nextSelection.revisionStartTime) >
        getTimestamp(latest.revisionStartTime)
        ? nextSelection
        : latest;
    }, null) ?? null
  );
};

export const getTreeBySelection = (
  trees: HardwareSelectorTree[],
  treeName: string,
): HardwareSelectorTree | null => {
  return trees.find(tree => tree.tree_name === treeName) ?? null;
};

export const getBranchBySelection = (
  tree: HardwareSelectorTree,
  gitRepositoryUrl: string,
  gitBranch: string,
): HardwareSelectorBranch | null => {
  return (
    tree.branches.find(branch => {
      return (
        branch.git_repository_url === gitRepositoryUrl &&
        branch.git_repository_branch === gitBranch
      );
    }) ?? null
  );
};

export const getRevisionBySelection = (
  branch: HardwareSelectorBranch,
  gitCommitHash: string,
): HardwareSelectorRevision | null => {
  return (
    branch.revisions.find(
      revision => revision.git_commit_hash === gitCommitHash,
    ) ?? null
  );
};

export const resolveHardwareSelection = ({
  trees,
  selectionFromUrl,
  hasSelectionParams,
}: {
  trees: HardwareSelectorTree[];
  selectionFromUrl: HardwareRevisionSelection | null;
  hasSelectionParams: boolean;
}): ResolvedHardwareSelection => {
  if (trees.length === 0) {
    return {
      selection: null,
      revisionStartTime: null,
      wasReset: false,
    };
  }

  if (selectionFromUrl !== null) {
    const selectedTree = getTreeBySelection(trees, selectionFromUrl.treeName);
    if (selectedTree !== null) {
      const selectedBranch = getBranchBySelection(
        selectedTree,
        selectionFromUrl.gitRepositoryUrl,
        selectionFromUrl.gitBranch,
      );

      if (selectedBranch !== null) {
        const selectedRevision = getRevisionBySelection(
          selectedBranch,
          selectionFromUrl.gitCommitHash,
        );

        if (selectedRevision !== null) {
          return {
            selection: selectionFromUrl,
            revisionStartTime: selectedRevision.start_time,
            wasReset: false,
          };
        }
      }
    }
  }

  const globalSelection = getGlobalLatestHardwareSelection(trees);
  if (globalSelection === null) {
    return {
      selection: null,
      revisionStartTime: null,
      wasReset: false,
    };
  }

  return {
    selection: globalSelection.selection,
    revisionStartTime: globalSelection.revisionStartTime,
    wasReset: hasSelectionParams,
  };
};

export const getSelectionForTreeChange = ({
  trees,
  treeName,
}: {
  trees: HardwareSelectorTree[];
  treeName: string;
}): HardwareRevisionSelection | null => {
  const selectedTree = getTreeBySelection(trees, treeName);
  if (selectedTree === null) {
    return null;
  }

  const selectedBranch = getLatestBranch(selectedTree.branches);
  if (selectedBranch === null) {
    return null;
  }

  const selectedRevision = getLatestRevision(selectedBranch.revisions);
  if (selectedRevision === null) {
    return null;
  }

  return {
    treeName: selectedTree.tree_name,
    gitRepositoryUrl: selectedBranch.git_repository_url,
    gitBranch: selectedBranch.git_repository_branch,
    gitCommitHash: selectedRevision.git_commit_hash,
  };
};

export const getSelectionForBranchChange = ({
  tree,
  gitRepositoryUrl,
  gitBranch,
}: {
  tree: HardwareSelectorTree;
  gitRepositoryUrl: string;
  gitBranch: string;
}): HardwareRevisionSelection | null => {
  const selectedBranch = getBranchBySelection(
    tree,
    gitRepositoryUrl,
    gitBranch,
  );
  if (selectedBranch === null) {
    return null;
  }

  const selectedRevision = getLatestRevision(selectedBranch.revisions);
  if (selectedRevision === null) {
    return null;
  }

  return {
    treeName: tree.tree_name,
    gitRepositoryUrl: selectedBranch.git_repository_url,
    gitBranch: selectedBranch.git_repository_branch,
    gitCommitHash: selectedRevision.git_commit_hash,
  };
};
