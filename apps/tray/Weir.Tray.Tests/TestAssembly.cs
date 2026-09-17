using Xunit;

// These tests deliberately replace WEIR_HOME, which is process-global. Running
// their classes concurrently can redirect one test's log or settings into another
// test's temporary directory and make otherwise-correct assertions race.
[assembly: CollectionBehavior(DisableTestParallelization = true)]
