# Software requirements — Ring buffer

- SWR-1: The ring buffer shall store up to `capacity` elements. Verification: test
- SWR-2: Pushing into a full buffer shall fail and leave the buffer unchanged. Verification: test
- SWR-3: Popping from an empty buffer shall fail. Verification: test
- SWR-4: The buffer shall be lock-free for a single producer / single consumer. Verification: analysis
