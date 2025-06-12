# Apollo CM testing webapp

A flexible, Docker-ready Flask app for logging Apollo Command Module test results with file uploads and CSV export.

## Features

- User login and registration
- Dynamic field configuration
- File upload with unique filenames
- Submission history and CSV export
- SQLite backend, Docker support

## Running via Docker

```bash
docker build -t test-logger .
docker run -p 5001:5001 -v $(pwd)/uploads:/app/uploads test-logger
```


Then visit: http://localhost:5001
Default login: `admin` / `password`
