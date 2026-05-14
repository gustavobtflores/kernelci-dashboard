import { useMemo, type JSX } from 'react';
import { FormattedMessage } from 'react-intl';

import { useNavigate, useSearch } from '@tanstack/react-router';

import { Toaster } from '@/components/ui/toaster';

import type { HardwareItem } from '@/types/hardware';

import {
  useHardwareListingByRevision,
  useHardwareSelectors,
} from '@/api/hardware';

import { dateObjectToTimestampInSeconds, daysToSeconds } from '@/utils/date';

import {
  includesInAnStringOrStringArray,
  matchesRegexOrIncludes,
} from '@/lib/string';

import { MemoizedKcidevFooter } from '@/components/Footer/KcidevFooter';
import { REDUCED_TIME_SEARCH } from '@/utils/constants/general';

import type { HardwareListingRoutesMap } from '@/utils/constants/hardwareListing';

import { HardwareTable } from './HardwareTable';
import { HardwareRevisionSelectors } from './HardwareRevisionSelectors';
import {
  decodeBranchValue,
  getBranchBySelection,
  getSelectionForBranchChange,
  getSelectionForTreeChange,
  getTreeBySelection,
  resolveHardwareSelection,
} from './hardwareSelection';

interface HardwareListingPageV2Props {
  inputFilter: string;
  urlFromMap: HardwareListingRoutesMap['v2'];
}

const HardwareListingPageV2 = ({
  inputFilter,
  urlFromMap,
}: HardwareListingPageV2Props): JSX.Element => {
  const navigate = useNavigate({ from: urlFromMap.navigate });
  const { origin, treeName, gitRepositoryUrl, gitBranch, gitCommitHash } =
    useSearch({ from: urlFromMap.search });

  const {
    data: selectorsData,
    error: selectorsError,
    status: selectorsStatus,
  } = useHardwareSelectors(urlFromMap.search);
  const selectors = useMemo(() => selectorsData?.trees ?? [], [selectorsData]);

  const hasSelectionParams = Boolean(
    treeName || gitRepositoryUrl || gitBranch || gitCommitHash,
  );

  const resolvedSelection = useMemo(() => {
    const selectionFromUrl =
      treeName && gitRepositoryUrl && gitBranch && gitCommitHash
        ? {
            treeName,
            gitRepositoryUrl,
            gitBranch,
            gitCommitHash,
          }
        : null;

    return resolveHardwareSelection({
      trees: selectors,
      selectionFromUrl,
      hasSelectionParams,
    });
  }, [
    selectors,
    treeName,
    gitRepositoryUrl,
    gitBranch,
    gitCommitHash,
    hasSelectionParams,
  ]);

  const {
    data: listingData,
    error: listingError,
    status: listingStatus,
    isLoading: isListingLoading,
  } = useHardwareListingByRevision(
    resolvedSelection.selection,
    urlFromMap.search,
  );

  const selectedTree = useMemo(() => {
    if (resolvedSelection.selection === null) {
      return null;
    }

    return getTreeBySelection(selectors, resolvedSelection.selection.treeName);
  }, [selectors, resolvedSelection.selection]);

  const selectedBranch = useMemo(() => {
    if (resolvedSelection.selection === null || selectedTree === null) {
      return null;
    }

    return getBranchBySelection(
      selectedTree,
      resolvedSelection.selection.gitRepositoryUrl,
      resolvedSelection.selection.gitBranch,
    );
  }, [resolvedSelection.selection, selectedTree]);

  const listItems: HardwareItem[] = useMemo(() => {
    if (!listingData || listingError) {
      return [];
    }

    const currentData = listingData.hardware;

    return currentData
      .filter(hardware => {
        return (
          matchesRegexOrIncludes(hardware.platform, inputFilter) ||
          includesInAnStringOrStringArray(hardware.hardware ?? '', inputFilter)
        );
      })
      .sort((a, b) => a.platform.localeCompare(b.platform));
  }, [listingData, listingError, inputFilter]);

  const revisionStartTimestampInSeconds = resolvedSelection.revisionStartTime
    ? dateObjectToTimestampInSeconds(
        new Date(resolvedSelection.revisionStartTime),
      )
    : 0;

  const revisionEndTimestampInSeconds = revisionStartTimestampInSeconds
    ? revisionStartTimestampInSeconds + daysToSeconds(REDUCED_TIME_SEARCH)
    : 0;

  const kcidevComponent = useMemo(
    () => (
      <MemoizedKcidevFooter
        commandGroup="hardwareListing"
        args={{ cmdName: 'hardware list', origin: origin, json: true }}
      />
    ),
    [origin],
  );

  const onTreeChange = (nextTreeName: string): void => {
    const nextSelection = getSelectionForTreeChange({
      trees: selectors,
      treeName: nextTreeName,
    });
    if (nextSelection === null) {
      return;
    }

    navigate({
      search: previousSearch => ({
        ...previousSearch,
        treeName: nextSelection.treeName,
        gitRepositoryUrl: nextSelection.gitRepositoryUrl,
        gitBranch: nextSelection.gitBranch,
        gitCommitHash: nextSelection.gitCommitHash,
      }),
      state: s => s,
    });
  };

  const onBranchChange = (branchValue: string): void => {
    if (selectedTree === null) {
      return;
    }

    const branchSelection = decodeBranchValue(branchValue);
    if (branchSelection === null) {
      return;
    }

    const nextSelection = getSelectionForBranchChange({
      tree: selectedTree,
      gitRepositoryUrl: branchSelection.gitRepositoryUrl,
      gitBranch: branchSelection.gitBranch,
    });
    if (nextSelection === null) {
      return;
    }

    navigate({
      search: previousSearch => ({
        ...previousSearch,
        treeName: nextSelection.treeName,
        gitRepositoryUrl: nextSelection.gitRepositoryUrl,
        gitBranch: nextSelection.gitBranch,
        gitCommitHash: nextSelection.gitCommitHash,
      }),
      state: s => s,
    });
  };

  const onRevisionChange = (nextGitCommitHash: string): void => {
    navigate({
      search: previousSearch => ({
        ...previousSearch,
        gitCommitHash: nextGitCommitHash,
      }),
      state: s => s,
    });
  };

  const hasSelectors = selectors.length > 0;
  const hasListingRows = Boolean((listingData?.hardware.length ?? 0) > 0);
  const tableEmptyMessageId =
    !hasListingRows && inputFilter.length === 0
      ? 'hardwareListing.revisionEmpty'
      : 'hardwareListing.notFound';

  return (
    <>
      <Toaster />
      <div className="flex flex-col gap-6">
        {selectorsStatus === 'error' && (
          <div className="w-full py-6 text-center">
            <span className="text-weak-gray text-sm">
              {selectorsError?.message}
            </span>
          </div>
        )}

        {selectorsStatus === 'pending' && (
          <div className="w-full py-6 text-center">
            <FormattedMessage id="global.loading" />
          </div>
        )}

        {selectorsStatus === 'success' && (
          <>
            {!hasSelectors && (
              <div className="text-weak-gray flex flex-col items-center py-10 text-center text-lg font-semibold">
                <FormattedMessage id="hardwareListing.selectorsNoData" />
              </div>
            )}

            {hasSelectors && (
              <>
                <HardwareRevisionSelectors
                  selectors={selectors}
                  selectedTree={selectedTree}
                  selectedBranch={selectedBranch}
                  selection={resolvedSelection.selection}
                  onTreeChange={onTreeChange}
                  onBranchChange={onBranchChange}
                  onRevisionChange={onRevisionChange}
                />

                {!hasListingRows &&
                  inputFilter.length === 0 &&
                  listingStatus === 'success' && (
                    <p className="text-weak-gray text-sm">
                      <FormattedMessage id="hardwareListing.revisionEmpty" />
                    </p>
                  )}

                <HardwareTable
                  treeTableRows={listItems}
                  endTimestampInSeconds={revisionEndTimestampInSeconds}
                  startTimestampInSeconds={revisionStartTimestampInSeconds}
                  status={listingStatus}
                  queryData={listingData}
                  error={listingError}
                  isLoading={isListingLoading}
                  navigateFrom={urlFromMap.navigate}
                  showTimeFilterInput={false}
                  emptyMessageId={tableEmptyMessageId}
                />
              </>
            )}
          </>
        )}
      </div>
      {kcidevComponent}
    </>
  );
};

export default HardwareListingPageV2;
