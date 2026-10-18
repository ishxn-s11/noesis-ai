"""One request-owned worker; no infinite polling loop on Vercel."""
import sys

if __name__ == "__main__":
    from workers.runner import handle_job
    handle_job(sys.argv[1])
