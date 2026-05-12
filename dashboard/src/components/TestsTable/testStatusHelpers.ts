import type { TIndividualTest, TPathTests } from '@/types/general';
import { StatusTable } from '@/utils/constants/database';

export type TPathTestsStatus = Pick<
  TPathTests,
  | 'done_tests'
  | 'error_tests'
  | 'fail_tests'
  | 'miss_tests'
  | 'pass_tests'
  | 'skip_tests'
  | 'null_tests'
  | 'total_tests'
>;

export type GroupNode = {
  done_tests: number;
  fail_tests: number;
  miss_tests: number;
  pass_tests: number;
  null_tests: number;
  skip_tests: number;
  error_tests: number;
  total_tests: number;
  individual_tests: TIndividualTest[];
  children: Map<string, GroupNode>;
};

export const getTotalTests = (
  group: Omit<TPathTestsStatus, 'total_tests'>,
): number =>
  group.done_tests +
  group.error_tests +
  group.fail_tests +
  group.miss_tests +
  group.pass_tests +
  group.null_tests +
  group.skip_tests;

export const countStatus = (group: TPathTestsStatus, status?: string): void => {
  switch (status?.toUpperCase()) {
    case StatusTable.DONE:
      group.done_tests++;
      break;
    case StatusTable.ERROR:
      group.error_tests++;
      break;
    case StatusTable.FAIL:
      group.fail_tests++;
      break;
    case StatusTable.MISS:
      group.miss_tests++;
      break;
    case StatusTable.PASS:
      group.pass_tests++;
      break;
    case StatusTable.SKIP:
      group.skip_tests++;
      break;
    default:
      group.null_tests++;
  }
};

export const addCounts = (
  target: TPathTestsStatus,
  source: TPathTestsStatus,
): void => {
  target.done_tests += source.done_tests;
  target.error_tests += source.error_tests;
  target.fail_tests += source.fail_tests;
  target.miss_tests += source.miss_tests;
  target.pass_tests += source.pass_tests;
  target.null_tests += source.null_tests;
  target.skip_tests += source.skip_tests;
};

export const createEmptyGroupStatusCounts = (): TPathTestsStatus => ({
  done_tests: 0,
  fail_tests: 0,
  miss_tests: 0,
  pass_tests: 0,
  null_tests: 0,
  skip_tests: 0,
  error_tests: 0,
  total_tests: 0,
});

export const createEmptyNode = (): GroupNode => ({
  ...createEmptyGroupStatusCounts(),
  individual_tests: [],
  children: new Map(),
});
