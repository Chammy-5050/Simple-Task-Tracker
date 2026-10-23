from django.core.exceptions import ValidationError


class PasswordComplexityValidator:
    """Require uppercase, lowercase, a digit, and a special character."""

    def validate(self, password, user=None):
        errors = []
        if not any(character.isupper() for character in password):
            errors.append("Password must contain at least one uppercase letter.")
        if not any(character.islower() for character in password):
            errors.append("Password must contain at least one lowercase letter.")
        if not any(character.isdecimal() for character in password):
            errors.append("Password must contain at least one number.")
        if not any(
            not character.isalnum() and not character.isspace()
            for character in password
        ):
            errors.append("Password must contain at least one special character.")
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return (
            "Your password must contain at least one uppercase letter, "
            "one lowercase letter, one number, and one special character."
        )
