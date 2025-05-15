# Linux Kernel Knowledge Graph

This project extracts and links entities from Linux kernel documentation to create a comprehensive knowledge graph.

## Overview

The Linux Kernel Knowledge Graph project aims to systematically extract entities and relationships from the Linux kernel documentation and source code, link them to external knowledge bases, and build a structured knowledge graph for improved understanding and navigation of the kernel.

## Key Components

### Entity Extraction

The system extracts important entities from kernel documentation, feature descriptions, and code comments.

### Entity Linking

The entity linking component connects extracted entities to Wikipedia articles, providing additional context and standardized definitions.

## How to Run

### Entity Linking

To link extracted entities to Wikipedia, run:

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

## Contributing

Contributions to improve the knowledge graph are welcome! Please open an issue or submit a pull request.
