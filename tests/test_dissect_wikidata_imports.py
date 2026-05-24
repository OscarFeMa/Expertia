"""Test that dissect_wikidata modules can be imported without errors."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + '/..')


def test_imports():
    """Test that key modules can be imported."""
    # Test settings
    from config.settings import (
        WIKIDATA_DUMP_PATH,
        WIKIDATA_OUTPUT_DIR,
        WIKIDATA_EXTRACTION_TIMEOUT_HOURS,
    )
    assert WIKIDATA_DUMP_PATH is not None
    assert WIKIDATA_OUTPUT_DIR is not None
    assert WIKIDATA_EXTRACTION_TIMEOUT_HOURS is not None
    
    # Test dissect_wikidata
    from dissect_wikidata import (
        WikidataStreamingExtractor,
        TAG_TO_QID_MAP,
        get_active_specialists,
        is_specialist_inoculated,
        handle_extraction_failure,
        main
    )
    assert WikidataStreamingExtractor is not None
    assert TAG_TO_QID_MAP is not None
    assert len(TAG_TO_QID_MAP) > 0
    # Check a few known mappings
    assert TAG_TO_QID_MAP.get('mathematics') == 'Q395'
    assert TAG_TO_QID_MAP.get('physics') == 'Q413'
    assert TAG_TO_QID_MAP.get('medicine') == 'Q11190'
    
    print("OK Dissect Wikidata imports successful!")


if __name__ == "__main__":
    test_imports()