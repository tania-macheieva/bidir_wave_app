# Bidirectional & Unidirectional Wave Search

A Python desktop application demonstrating and comparing **bidirectional and unidirectional wave search** algorithms in a maze.

The maze is generated automatically, but can also be edited manually.

## Features

* Generate mazes with configurable size, wall density and seed.
* Select the start and target vertices.
* Add and remove walls manually.
* Choose cross, diagonal or combined movement.
* Run bidirectional or unidirectional wave search.
* Visualize wave propagation from the start and target.
* Display the meeting point, found path and search statistics.
* Compare both algorithms and all movement operators under the same conditions.
* Run the search with or without animation.

## Algorithms

* **Bidirectional Wave Search** explores the maze simultaneously from the start and target until the two waves meet.
* **Unidirectional Wave Search** explores the maze level by level from the start to the target.
* Both algorithms find the shortest path in an unweighted graph.

## Technologies

* Python 3
* Tkinter
* `dataclasses`
* `typing`
* `time`

## Running

```bash
python3 bidirectional_wave_search.py
```
