import json
import os

def process_entities(input_path, output_path):
    """
    Processes a JSON file of entities to extract key information.

    It creates a map where keys are the entity's name and aliases,
    and values are the entity's context and external URLs.

    Args:
        input_path (str): The path to the input JSON file.
        output_path (str): The path to save the processed JSON file.
    """
    print(f"Starting processing of {input_path}...")

    # Ensure the output directory exists
    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")

    processed_data = {}

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for entity in data:
            # Extract context, handle if missing
            context = entity.get('context', '')
            description = entity.get('description', '')
            # Extract URLs from external_links, handle if missing or not a list
            external_links = entity.get('external_links')

            if isinstance(external_links, list):
                url = external_links[0]['url'][0]
            else:
                url = ''

            value_data = {
                'context': context,
                'description': description,
                'url': url
            }

            # Collect all keys (name + aliases)
            keys = []
            if 'name' in entity and entity['name']:
                keys.append(entity['name'])
            
            aliases = entity.get('aliases')
            if isinstance(aliases, list):
                keys.extend(aliases)

            # Populate the processed_data dictionary
            for key in keys:
                if key: # Ensure key is not empty
                    processed_data[key] = value_data

        # Save the processed data to the output file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, indent=4, ensure_ascii=False)

        print(f"Successfully processed file.")
        print(f"Output saved to {output_path}")

    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}")
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {input_path}. The file might be corrupted or not in valid JSON format.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    # Define file paths
    # Assuming the script is run from the root of the project directory
    INPUT_JSON_PATH = 'output/entity_linking/linked_entities_gpt_0521.json'
    OUTPUT_JSON_PATH = 'output/processed_entities_for_CL.json'
    
    process_entities(INPUT_JSON_PATH, OUTPUT_JSON_PATH) 