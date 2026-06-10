# Get Energy Traces

Fetches ENTSO-E generation data and creates carbon and water intensity CSV
profiles.

## Setup

```bash
python -m pip install -r requirements.txt
```

Create a `.env` file:

```text
API_TOKEN=your-entsoe-token
```

## Usage

Generate an average yearly profile:

```bash
python year_script.py DE 2018 2025 --resolution 15
```

Generated CSV files are written to `outputs/`.
