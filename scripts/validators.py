"""
Input validation module for the RAG Chat system.
Provides validation functions for figure creation and editing.
"""

import re
from typing import Dict, Any, Tuple, Optional

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def validate_figure_id(figure_id: str) -> Tuple[bool, Optional[str]]:
    """
    Validate figure ID format.
    Must contain only letters (no special characters or spaces).
    
    Args:
        figure_id: The figure ID to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not figure_id:
        return False, "Figure ID is required"
    
    if len(figure_id) > 50:
        return False, "Figure ID must be 50 characters or less"
    
    # Only allow letters (uppercase and lowercase)
    if not re.match(r'^[a-zA-Z]+$', figure_id):
        return False, "Figure ID must contain only alphabetic characters (no numbers, spaces, or special characters)"
    
    return True, None

def validate_figure_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate figure name.
    Allows alphabetic characters (including Unicode/Chinese) and spaces.
    
    Args:
        name: The figure name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Figure name is required"
    
    if len(name) > 100:
        return False, "Figure name must be 100 characters or less"
    
    # Check for invalid characters (numbers, special characters except spaces)
    # Allow Unicode letters including Chinese characters
    if re.search(r'[0-9!@#$%^&*()_+=\[\]{};:\'",.<>?/\\|`~]', name):
        return False, "Figure name must contain only alphabetic characters and spaces"
    
    return True, None

def validate_description(description: str) -> Tuple[bool, Optional[str]]:
    """
    Validate figure description.
    Must be 400 characters or less.
    
    Args:
        description: The description to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if description and len(description) > 400:
        return False, "Description must be 400 characters or less"
    
    return True, None

def validate_personality_prompt(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Validate personality prompt.
    Must be 400 characters or less.
    
    Args:
        prompt: The personality prompt to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if prompt and len(prompt) > 400:
        return False, "Personality prompt must be 400 characters or less"
    
    return True, None

def validate_year(year_str: str, field_name: str = "Year") -> Tuple[bool, Optional[str]]:
    """
    Validate year format.
    Must be a 4-digit number.
    
    Args:
        year_str: The year string to validate
        field_name: Name of the field for error messages
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not year_str:
        return True, None  # Year is optional
    
    # Check if it's a valid integer
    try:
        year = int(year_str)
    except ValueError:
        return False, f"{field_name} must be a number"
    
    # Check if it's 4 digits
    if not (1000 <= year <= 9999):
        return False, f"{field_name} must be a 4-digit number (e.g., 1950)"
    
    # Reasonable range check
    if not (-3000 <= year <= 2100):
        return False, f"{field_name} must be between 3000 BC and 2100 AD"
    
    return True, None

def validate_figure_data(data: Dict[str, Any], is_update: bool = False) -> Dict[str, str]:
    """
    Validate all figure data.
    
    Args:
        data: Dictionary containing figure data
        is_update: Whether this is an update (some fields optional) or creation
        
    Returns:
        Dictionary of validation errors (empty if all valid)
    """
    errors = {}
    
    # Validate figure_id (only for creation)
    if not is_update:
        figure_id = data.get('figure_id', '').strip()
        valid, error = validate_figure_id(figure_id)
        if not valid:
            errors['figure_id'] = error
    
    # Validate name
    name = data.get('name', '').strip()
    if not is_update or name:  # Required for creation, optional for update
        valid, error = validate_figure_name(name)
        if not valid:
            errors['name'] = error
    
    # Validate description
    description = data.get('description', '').strip()
    valid, error = validate_description(description)
    if not valid:
        errors['description'] = error
    
    # Validate personality prompt
    personality_prompt = data.get('personality_prompt', '').strip()
    valid, error = validate_personality_prompt(personality_prompt)
    if not valid:
        errors['personality_prompt'] = error
    
    # Validate birth year
    birth_year = data.get('birth_year', '').strip()
    if birth_year:
        valid, error = validate_year(birth_year, "Birth year")
        if not valid:
            errors['birth_year'] = error
    
    # Validate death year
    death_year = data.get('death_year', '').strip()
    if death_year:
        valid, error = validate_year(death_year, "Death year")
        if not valid:
            errors['death_year'] = error
    
    # Cross-field validation
    if birth_year and death_year:
        try:
            birth = int(birth_year)
            death = int(death_year)
            if death < birth:
                errors['death_year'] = "Death year cannot be before birth year"
        except ValueError:
            pass  # Already caught above
    
    # Validate nationality (optional, but if provided, should be alphabetic)
    nationality = data.get('nationality', '').strip()
    if nationality and not re.match(r'^[a-zA-Z\s\-\']+$', nationality):
        errors['nationality'] = "Nationality must contain only letters, spaces, hyphens, and apostrophes"
    
    # Validate occupation (optional, basic check)
    occupation = data.get('occupation', '').strip()
    if occupation and len(occupation) > 200:
        errors['occupation'] = "Occupation must be 200 characters or less"
    
    return errors

def sanitize_figure_id(figure_id: str) -> str:
    """
    Sanitize figure ID by removing invalid characters.
    
    Args:
        figure_id: The figure ID to sanitize
        
    Returns:
        Sanitized figure ID
    """
    # Remove all non-alphabetic characters
    sanitized = re.sub(r'[^a-zA-Z]', '', figure_id)
    
    # Convert to lowercase for consistency
    sanitized = sanitized.lower()
    
    # Limit length
    return sanitized[:50]

def sanitize_figure_name(name: str) -> str:
    """
    Sanitize figure name by removing invalid characters.
    Allows Unicode letters (including Chinese characters) and spaces.
    
    Args:
        name: The figure name to sanitize
        
    Returns:
        Sanitized figure name
    """
    # Remove only specific invalid characters (numbers and special characters)
    # This preserves all Unicode letters including Chinese characters
    sanitized = re.sub(r'[0-9!@#$%^&*()_+=\[\]{};:\'",.<>?/\\|`~\-]', '', name)
    
    # Remove multiple spaces
    sanitized = ' '.join(sanitized.split())
    
    # Limit length
    return sanitized[:100]
