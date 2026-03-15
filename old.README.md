Create a clean scaffold for a multiplayer 2D horror game using Python and pygame.

This is a university Software Engineering group project, so the code must prioritize:
- readability
- modular structure
- clear comments
- docstrings explaining each system
- simple architecture that teammates can easily understand

Game Concept:

Players explore a 2D side-view research facility (similar to a platform-style side perspective).

Movement happens in:
- X axis (left/right)
- Y axis (floors, ladders, platforms)

The environment is viewed from the side, not top-down.

Players cooperate to explore the facility while a Mimic Entity learns player movement patterns and attempts to blend in and attack.

The focus is on:
- strategy
- communication
- uncertainty
- horror through sound and limited visibility.

Technical Requirements:

1. Use pygame for the client game.
2. Implement a small Python multiplayer server.
3. Networking should be simple and understandable (socket-based or asyncio).
4. The server should manage:
   - connected players
   - player positions
   - mimic entity state
   - broadcast game state updates.

5. The client should handle:
   - rendering
   - player input
   - sending player movement to server
   - receiving updates.

Project Structure:

Generate a clean folder structure like this:

game/
    main.py
    config.py
    README.md

    client/
        client_network.py
        game_client.py

    server/
        game_server.py
        server_network.py

    entities/
        player.py
        mimic.py

    systems/
        movement_system.py
        sound_system.py
        behavior_tracker.py

    map/
        facility_map.py

    rendering/
        renderer.py
        camera.py

Code Requirements:

- Each file should include a short header comment explaining its purpose.
- Each class should include docstrings describing what it does.
- Avoid overly complex patterns.
- Keep logic straightforward and easy to follow.

Gameplay Prototype Requirements:

1. Create a simple side-view test map.
2. Allow players to move left/right and climb ladders.
3. Display multiple players in the same world.
4. Implement a basic Mimic entity that moves randomly for now.
5. Server broadcasts player positions 10–20 times per second.
6. Client renders all players.

Networking:

- Use TCP sockets.
- Keep message format simple (JSON messages).
- Include message types like:
    PLAYER_JOIN
    PLAYER_MOVE
    GAME_STATE

Sound System:

Include a simple placeholder sound manager class that can later support:
- proximity sound
- ambient horror sounds
- footsteps.

README Requirements:

Generate a README.md that explains:

- the game concept
- the project architecture
- how to run the server
- how to run the client
- how the networking works.

The goal is a clean, understandable scaffold that a team of students can build on.