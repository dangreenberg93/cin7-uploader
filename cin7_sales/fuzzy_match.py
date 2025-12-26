"""
Fuzzy matching utilities for customers and addresses
"""
from typing import List, Dict, Any, Tuple, Optional
from difflib import SequenceMatcher


def string_similarity(s1: str, s2: str) -> float:
    """
    Calculate similarity ratio between two strings (0.0 to 1.0).
    
    Args:
        s1: First string
        s2: Second string
    
    Returns:
        Similarity ratio (0.0 = completely different, 1.0 = identical)
    """
    if not s1 or not s2:
        return 0.0
    
    # Normalize strings (lowercase, strip whitespace)
    s1_normalized = s1.lower().strip()
    s2_normalized = s2.lower().strip()
    
    # Exact match after normalization
    if s1_normalized == s2_normalized:
        return 1.0
    
    # Use SequenceMatcher for fuzzy matching
    return SequenceMatcher(None, s1_normalized, s2_normalized).ratio()


def normalize_address(address_str: str) -> str:
    """
    Normalize an address string for comparison.
    
    Handles multi-line addresses by collapsing all whitespace (spaces, newlines, tabs)
    into single spaces. This allows fuzzy matching to work with addresses that come
    in various formats (single line, multi-line, with extra spaces, etc.)
    
    Example input:
        "Great South Bay Brewing Company
         25 Drexel Dr
         
         BAY SHORE NY 11706"
    
    Example output:
        "great south bay brewing company 25 drexel dr bay shore ny 11706"
    
    Args:
        address_str: Address string to normalize (may contain newlines, extra spaces)
    
    Returns:
        Normalized address string (single line, lowercase, collapsed whitespace)
    """
    if not address_str:
        return ""
    
    # Convert to lowercase, strip leading/trailing whitespace
    # .split() without arguments splits on ANY whitespace (spaces, newlines, tabs)
    # and removes empty strings, then join with single space
    # This effectively converts multi-line addresses to single-line
    normalized = " ".join(address_str.lower().strip().split())
    
    # Common abbreviations that should be normalized
    replacements = {
        "street": "st",
        "avenue": "ave",
        "road": "rd",
        "drive": "dr",
        "boulevard": "blvd",
        "lane": "ln",
        "court": "ct",
        "place": "pl",
        "north": "n",
        "south": "s",
        "east": "e",
        "west": "w",
    }
    
    # Apply replacements (simple word boundary matching)
    for full, abbrev in replacements.items():
        normalized = normalized.replace(f" {full} ", f" {abbrev} ")
        normalized = normalized.replace(f" {full}.", f" {abbrev}.")
        if normalized.endswith(f" {full}"):
            normalized = normalized[:-len(f" {full}")] + f" {abbrev}"
    
    return normalized


def parse_address_string(address_str: str) -> Dict[str, str]:
    """
    Parse a multi-line address string into structured components.
    
    Attempts to parse common address formats like:
        "Company Name
         123 Street Address
         
         CITY STATE ZIPCODE"
    
    or:
        "123 Street Address
         CITY STATE ZIPCODE"
    
    Args:
        address_str: Address string (may be multi-line)
    
    Returns:
        Dictionary with keys: Company (optional), Line1, Line2 (optional), City, State, Postcode, Country
        If parsing fails, returns dict with 'Line1' set to normalized address
    """
    if not address_str:
        return {}
    
    # Split by newlines and filter out empty lines
    lines = [line.strip() for line in address_str.split('\n') if line.strip()]
    
    if not lines:
        return {}
    
    # Common pattern: Last line contains "CITY STATE ZIPCODE" or "CITY STATE ZIP"
    # Try to extract city/state/zip from last line
    result = {}
    
    # Try to parse last line for city/state/zip
    last_line = lines[-1].strip()
    
    # Pattern: "CITY STATE ZIPCODE" (e.g., "BAY SHORE NY 11706")
    # Try to match ZIP code pattern (5 digits or 5+4 format)
    import re
    zip_pattern = r'\b(\d{5}(?:-\d{4})?)\b'
    zip_match = re.search(zip_pattern, last_line)
    
    if zip_match:
        result['Postcode'] = zip_match.group(1)
        # Remove zip from last line
        remaining = last_line[:zip_match.start()].strip()
        
        # Try to split remaining into City and State
        # Look for 2-letter state code at the end
        state_pattern = r'\b([A-Z]{2})\b$'
        state_match = re.search(state_pattern, remaining)
        
        if state_match:
            result['State'] = state_match.group(1)
            result['City'] = remaining[:state_match.start()].strip()
        else:
            # No clear state pattern, treat entire remaining as city
            result['City'] = remaining
    else:
        # No zip code found, treat last line as city
        result['City'] = last_line
    
    # All lines except the last are address lines
    address_lines = lines[:-1]
    
    # First line might be company name if it doesn't contain numbers/address indicators
    if len(address_lines) > 0:
        first_line = address_lines[0]
        # Check if first line looks like a company name (no numbers, no common address words)
        address_indicators = ['street', 'st', 'avenue', 'ave', 'road', 'rd', 'drive', 'dr', 
                            'boulevard', 'blvd', 'lane', 'ln', 'court', 'ct', 'place', 'pl',
                            'suite', 'ste', 'unit', 'apt', 'apartment', '#']
        first_line_lower = first_line.lower()
        has_address_indicator = any(indicator in first_line_lower for indicator in address_indicators)
        has_numbers = any(c.isdigit() for c in first_line)
        
        # If first line doesn't look like an address and we have multiple lines, treat as company
        if not has_address_indicator and not has_numbers and len(address_lines) > 1:
            result['Company'] = first_line
            result['Line1'] = address_lines[1]
            if len(address_lines) > 2:
                result['Line2'] = address_lines[2]
        else:
            # First line is the address
            result['Line1'] = first_line
            if len(address_lines) > 1:
                result['Line2'] = address_lines[1]
    elif len(address_lines) == 0:
        # No address lines, use normalized address as Line1
        result['Line1'] = normalize_address(address_str).title()
    
    # Clean up: remove any None or empty values
    result = {k: v for k, v in result.items() if v}
    
    return result


def fuzzy_match_customer(customer_name: str, candidates: List[Dict[str, Any]], 
                        threshold: float = 0.85) -> Tuple[Optional[Dict[str, Any]], float, List[Tuple[Dict[str, Any], float]]]:
    """
    Find the best fuzzy match for a customer name from a list of candidates.
    
    Args:
        customer_name: Customer name to match
        candidates: List of candidate customer dictionaries (must have 'Name' field)
        threshold: Minimum similarity threshold (0.0 to 1.0). Default 0.85 (85% match)
    
    Returns:
        (best_match, best_score, all_matches_with_scores)
        - best_match: Best matching customer dict or None if no match above threshold
        - best_score: Similarity score of best match (0.0 to 1.0)
        - all_matches_with_scores: List of tuples (customer_dict, score) sorted by score (descending)
    """
    if not customer_name or not candidates:
        return None, 0.0, []
    
    matches = []
    
    for candidate in candidates:
        candidate_name = candidate.get('Name', '')
        if not candidate_name:
            continue
        
        score = string_similarity(customer_name, candidate_name)
        matches.append((candidate, score))
    
    # Sort by score (descending)
    matches.sort(key=lambda x: x[1], reverse=True)
    
    # Return best match if above threshold
    if matches and matches[0][1] >= threshold:
        return matches[0][0], matches[0][1], matches
    else:
        return None, matches[0][1] if matches else 0.0, matches


def fuzzy_match_address(address_str: str, candidate_addresses: List[Dict[str, Any]], 
                       threshold: float = 0.80) -> Tuple[Optional[Dict[str, Any]], float, List[Tuple[Dict[str, Any], float]]]:
    """
    Find the best fuzzy match for an address from a list of candidate addresses.
    
    Args:
        address_str: Address string to match
        candidate_addresses: List of candidate address dictionaries
        threshold: Minimum similarity threshold (0.0 to 1.0). Default 0.80 (80% match)
    
    Returns:
        (best_match, best_score, all_matches_with_scores)
        - best_match: Best matching address dict or None if no match above threshold
        - best_score: Similarity score of best match (0.0 to 1.0)
        - all_matches_with_scores: List of tuples (address_dict, score) sorted by score (descending)
    """
    if not address_str or not candidate_addresses:
        return None, 0.0, []
    
    # Normalize the input address
    normalized_input = normalize_address(address_str)
    
    matches = []
    
    for candidate in candidate_addresses:
        # Build address string from candidate (handle different address formats)
        candidate_parts = []
        
        # Common address fields in Cin7
        if candidate.get('Line1'):
            candidate_parts.append(candidate.get('Line1'))
        if candidate.get('Line2'):
            candidate_parts.append(candidate.get('Line2'))
        if candidate.get('City'):
            candidate_parts.append(candidate.get('City'))
        if candidate.get('State'):
            candidate_parts.append(candidate.get('State'))
        if candidate.get('Postcode'):
            candidate_parts.append(candidate.get('Postcode'))
        if candidate.get('Country'):
            candidate_parts.append(candidate.get('Country'))
        
        # Also check if there's a combined address string
        if not candidate_parts and candidate.get('DisplayAddress'):
            candidate_parts = [candidate.get('DisplayAddress')]
        
        if not candidate_parts:
            continue
        
        candidate_address = " ".join(str(p) for p in candidate_parts if p)
        normalized_candidate = normalize_address(candidate_address)
        
        score = string_similarity(normalized_input, normalized_candidate)
        matches.append((candidate, score))
    
    # Sort by score (descending)
    matches.sort(key=lambda x: x[1], reverse=True)
    
    # Return best match if above threshold
    if matches and matches[0][1] >= threshold:
        return matches[0][0], matches[0][1], matches
    else:
        return None, matches[0][1] if matches else 0.0, matches

