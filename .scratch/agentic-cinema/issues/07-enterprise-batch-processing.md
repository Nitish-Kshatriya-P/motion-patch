# 07: Enterprise Batch Processing (Cloud Run)

**What to build:** Prove enterprise scalability. Modify the React UI to allow uploading multiple `.bvh` files (capped at 5). The FastAPI backend dispatches each file as an asynchronous Cloud Run Job. The UI displays the processing status of all 5 files concurrently, and downloads the batch zip when complete.

**Blocked by:** 06

**Status:** done

- [x] React UI updated for multi-file upload and batch progress visualization
- [x] FastAPI integration with Google Cloud Run Jobs API to spin up concurrent workers
- [x] Hardcoded logic limiting batch size to 5 files to protect API budget
