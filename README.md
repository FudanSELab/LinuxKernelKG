# Linux Kernel Knowledge Graph

This project extracts and links entities from Linux kernel documentation to create a comprehensive knowledge graph.

## Overview

The Linux Kernel Knowledge Graph project aims to systematically extract entities and relationships from the Linux kernel documentation and source code, link them to external knowledge bases, and build a structured knowledge graph for improved understanding and navigation of the kernel.

## Key Components

### Entity Extraction

The system extracts important entities from kernel documentation, feature descriptions, and code comments.

### Entity Linking

The entity linking component connects extracted entities to Wikipedia articles, providing additional context and standardized definitions.

#### Wikipedia API 429 Error Handling

The system has been optimized to handle Wikipedia API rate limiting (429 errors) through:

- **Intelligent Rate Limiting**: Configurable request limits per minute/hour with automatic throttling
- **Retry with Exponential Backoff**: Automatic retry mechanism with increasing delays for failed requests
- **Request Deduplication**: Eliminates duplicate API calls to reduce unnecessary requests
- **Improved User-Agent**: Uses proper identification for educational/research purposes
- **Comprehensive Caching**: Enhanced caching to minimize redundant Wikipedia queries
- **Batch Processing Optimization**: Reduced batch sizes and added delays between batches

#### Configuration Options

Wikipedia API behavior can be configured in `config/pipeline_config.py`:

```python
WIKIPEDIA_RATE_LIMIT = {
    'max_requests_per_minute': 20,  # Conservative limit
    'max_requests_per_hour': 1200,  # Hourly limit
    'min_request_interval': 2.0,    # Minimum seconds between requests
    'retry_max_attempts': 3,        # Maximum retry attempts
    'retry_base_delay': 2.0,        # Base retry delay (seconds)
    'retry_max_delay': 120.0        # Maximum retry delay (seconds)
}

WIKIPEDIA_USER_AGENT = 'LinuxKernelKG/1.0 (Educational research project; Linux kernel knowledge graph; contact: admin@example.com) Python/3.x'

ENABLE_API_LOGGING = True           # Enable detailed API statistics
AUTO_ADJUST_RATE_LIMIT = True       # Auto-adjust on 429 errors
```

#### Best Practices for Avoiding 429 Errors

1. **Use Conservative Settings**: Start with lower request rates and increase gradually
2. **Monitor API Statistics**: Check logs for rate limiting warnings
3. **Respect Wikipedia Guidelines**: Ensure requests are for legitimate research purposes
4. **Use Proper User-Agent**: Include project information and contact details
5. **Enable Caching**: Leverage the built-in caching to reduce API calls

#### Troubleshooting Common Issues

##### Issue 1: Entity.__init__() TypeError

If you encounter: `TypeError: Entity.__init__() got an unexpected keyword argument 'commit_ids'`

**Solution**: The Entity class doesn't accept `commit_ids` in the constructor. Use this pattern instead:

```python
# ❌ Wrong way
entity = Entity(
    name="process",
    context="Linux kernel process management",
    feature_id=1001,
    commit_ids=["abc123"]  # This will cause an error
)

# ✅ Correct way  
entity = Entity(
    name="process",
    context="Linux kernel process management",
    feature_id=1001  # feature_id should be integer
)
entity.commit_ids = ["abc123"]  # Set commit_ids after creation
```

##### Issue 2: Network Connection Timeouts

If you see: `Connection to en.wikipedia.org timed out`

**Diagnosis**: Run the network connectivity test first:
```bash
python3 scripts/test_network_connectivity.py
```

**Solutions**:
1. **Check network access**: Ensure you can reach Wikipedia
2. **Configure proxy** (if needed):
   ```bash
   export HTTP_PROXY=your_proxy_url
   export HTTPS_PROXY=your_proxy_url
   ```
3. **Use VPN**: If Wikipedia is blocked in your region
4. **Increase timeouts**: Modify timeout settings in config

##### Issue 3: Still Getting 429 Errors

**Solutions**:
1. **Use more conservative settings**:
   ```python
   WIKIPEDIA_RATE_LIMIT = {
       'max_requests_per_minute': 8,  # Even more conservative
       'min_request_interval': 5.0,   # Longer intervals
   }
   ```
2. **Increase retry delays**:
   ```python
   WIKIPEDIA_RATE_LIMIT = {
       'retry_base_delay': 10.0,      # Longer base delay
       'retry_max_delay': 300.0       # 5 minutes max delay
   }
   ```

#### Quick Testing Guide

1. **Test Network Connection** (Always run first):
   ```bash
   ./test_wikipedia.sh
   # Choose option 1: Network connectivity test
   ```

2. **Run Quick Test**:
   ```bash
   ./test_wikipedia.sh  
   # Choose option 2: Quick test (2 entities)
   ```

3. **Check Results**:
   - ✅ Success: No 429 errors, proper request intervals
   - ❌ Network issues: Run connectivity test first
   - ❌ 429 errors: Use more conservative settings

## How to Run

### Entity Linking

#### With JSON File Output (Original)

To link extracted entities to Wikipedia and save to JSON file, run:

```bash
python scripts/run_entity_link.py
```

Options:

- `--input`, `-i`: Input file with extracted entities (default: output/entity_extraction/extraction_results_20250321_1058.jsonl)
- `--output`, `-o`: Output file for linked entities (default: output/entity_linking/linked_entities_{timestamp}.jsonl)
- `--batch-size`, `-b`: Batch size for processing entities (default: 10)

Example:

```bash
python scripts/run_entity_link.py --input output/entity_extraction/my_entities.jsonl --batch-size 20
```

#### With MySQL Database Storage (New)

To link extracted entities to Wikipedia and save to MySQL database, run:

```bash
python scripts/run_entity_link_db.py
```

Options:

- `--input`, `-i`: Input file with extracted entities (default: output/entity_extraction/extraction_results_20250509_0958.jsonl)
- `--batch-size`, `-b`: Batch size for processing entities (default: 10)
- `--max-feature-id`: Maximum feature_id to process (default: 33388)
- `--resume`: Resume from last processed feature_id in database (default: True)
- `--test-db`: Test database connection and exit

Examples:

```bash
# Test database connection
python scripts/run_entity_link_db.py --test-db

# Run with default settings (auto-resume enabled)
python scripts/run_entity_link_db.py

# Run with custom batch size and max feature_id
python scripts/run_entity_link_db.py --batch-size 20 --max-feature-id 50000

# Run without auto-resume (start from beginning)
python scripts/run_entity_link_db.py --no-resume
```

**Database Configuration**

The MySQL database connection is configured in `config/pipeline_config.py`:

```python
DB_CONFIG = {
    'host': '10.176.34.96',
    'port': 3306,
    'user': 'root',
    'password': '3edc@WSX!QAZ',
    'database': 'linuxDatabase',
    'charset': 'utf8mb4'
}
```

**Database Tables**

The system uses two main tables:

1. `entities_extraction`: Main entity table with fields like name_en, definition_en, aliases, feature_id, etc.
2. `entity_aliases`: Separate table for entity aliases with foreign key reference to entities_extraction

## Input/Output Formats

### Entity Extraction Output / Entity Linking Input

```json
{
  "feature_id": 30357,
  "feature": {
    "feature_id": 30357,
    "h1": "Drivers",
    "h2": "Storage",
    "feature_description": "SCSI ibmvfc: initial MQ development/enablement",
    "version": "5.12"
  },
  "extraction_result": {
    "filtered_entities": [
      "SCSI",
      "ibmvfc",
      "development",
      "enablement"
    ]
  }
}
```

### Entity Linking Output

Each linked entity is saved as a JSON object with details including:

- Entity name and ID
- Feature relationship
- Wikipedia links
- Description
- Aliases

## Architecture

The system follows a pipeline architecture:

1. Extract entities from kernel documentation and code
2. Link entities to external knowledge (Wikipedia)
3. Build relationships between entities
4. Create and store the knowledge graph

## Configuration

The system can be configured to use:

- Local or online Wikipedia for entity linking
- Different LLM providers for entity processing
- Various batch sizes and optimization parameters

## Performance Considerations

- Entity linking is a resource-intensive process, especially with large input files
- Use batching to process entities in manageable chunks
- Consider using a local Wikipedia mirror for faster processing

## Recent Updates

### MySQL Database Storage Support

Added support for storing entity linking results directly to MySQL database instead of JSON files:

- **New Script**: `scripts/run_entity_link_db.py` - Entity linking with MySQL storage
- **Database Manager**: `database/mysql_manager.py` - MySQL connection and data operations
- **Resume Capability**: Automatically resumes from last processed feature_id
- **Batch Processing**: Efficient batch insertion with error handling
- **Alias Support**: Proper handling of entity aliases in separate table

### Testing

- **Database Test**: `scripts/test_db_connection.py` - Test database connectivity
- **Connection Validation**: Built-in database connection testing before processing
- **Demo Script**: `examples/entity_linking_database_demo.py` - Comprehensive demo of database functionality
- **Cleanup Script**: `scripts/cleanup_demo_data.py` - Clean up demo and test data

#### Running the Demo

```bash
# Run the complete database functionality demo
python examples/entity_linking_database_demo.py

# Clean up demo data afterwards
python scripts/cleanup_demo_data.py
```

## Contributing

Contributions to improve the knowledge graph are welcome! Please open an issue or submit a pull request.
