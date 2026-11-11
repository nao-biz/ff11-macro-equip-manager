"""Project committed export names onto a detached presentation snapshot."""


def apply_names(snapshot, observations):
    for character in snapshot.characters:
        observation = observations.get(character.folder_id)
        if observation is not None:
            character.display_name = observation.export.character_name
            character.identity_status = 'export_verified'
