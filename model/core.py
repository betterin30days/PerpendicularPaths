import random
import copy
import time
from .primative import Shared, Point, Board, Goal
from .BoardGenerator import BoardGenerator
from .SolutionGenerator import SolutionGenerator

class State(object):
    """Current mode of 'PerpendicularPaths'"""
    play = 0b00000010
    game_over = 0b00010000
    level_complete = 0b10000000
    game_restart = 0b01000000
    game_complete = 0b00001000

class PPMoveStatus(object):
    """description of return state of us 'PerpendicularPaths'.robot_move"""
    MOVE_SUCCESS = 0
    PERPENDICULAR_MOVE_REQUIRED = 1
    CANNOT_MOVE_DIRECTION = 2
    PERPENDICULAR_BEFORE_GOAL = 3

class PerpendicularPaths:
    board_section = None
    solver = None
    __boardgenerator = None
    game_state = 0

    robots_location = {}
    __robots_starting_location = {}
    game_move_count = 0
    game_time_count = 0
    level_time = 0
    move_history = []
        #robot, direction, old cell, new cell
    goal_index = 0
    config = None
    #access to defaults
    is_perpendicular_mode = True
    #Controls enforement of move rules

    def __init__(self):
        self.config = Shared.config()
        self.game_state = State.game_restart
        self.__boardgenerator = BoardGenerator()

    def __board_generate(
            self, boards=None, robots=None,
            goals=None, dimension=None, goal_count=None,
            is_perpendicular_mode=True):
        """
        boards = list of 'board'.key values (string)
        robots = list of tuple (Robot, Point)
        goals = list of 'goal'
        goal_count = number of goals for game up to len(boardgenerator.board_section.goals)
        """
        if goal_count is None:
            goal_count = int(self.config['model']['robot_count_default'])
        assert goal_count is not None
        self.board_section = self.__boardgenerator.generate(boards, dimension)
        self.solver = SolutionGenerator(
            self.board_section,
            Shared.ROBOTS,
            Shared.DIRECTIONS)
        self.solver.is_perpendicular_mode = is_perpendicular_mode
        self.__robots_generate(robots)
        random.shuffle(self.board_section.goals)
        if goals is None:
            goals = []
        goal_count = min(goal_count, len(self.board_section.goals))
        goals += self.board_section.goals[0:goal_count-len(goals)]
        self.board_section = Board(
            self.board_section.key,
            self.board_section.board,
            goals)

    def __robots_generate(self, robots=None):
        """robots = list of tuple (Robot, Point)"""
        self.__robots_starting_location = {}
        if robots is not None:
            for robot in robots:
                self.__robots_starting_location[robot[0]] = robot[1]
        for robot in Shared.ROBOTS:
            if self.__robots_starting_location.get(robot) is None:
                robot_placement_attempts = 0
                try_again = True
                while try_again:
                    new_point = Point(
                        random.randint(0, self.board_section.width - 1),
                        random.randint(0, self.board_section.height - 1))
                    if new_point.x not in(7, 8) and new_point.y not in(7, 8):
                        try_again = False
                        for goal in self.board_section.goals:
                            if goal.point == new_point:
                                try_again = True
                                break
                        for robot_placed in self.__robots_starting_location:
                            if self.__robots_starting_location[robot_placed] == new_point:
                                try_again = True
                                break
                    assert robot_placement_attempts < 50
                    robot_placement_attempts += 1
                self.__robots_starting_location[robot] = new_point

    def __cell_move(self, point, direction, robot):
        if self.board_section.board_value(point) & direction.value:
            #Wall in point stopping us
            return point
        advanced_cell = copy.copy(point)
        advanced_cell.move(direction)
        for _robot in self.robots_location:
            if advanced_cell == self.robots_location[_robot]:
                #blocked by robot in next point
                return point
        return self.__cell_move(advanced_cell, direction, robot)

    def move_undo(self):
        """Remove the last move from history"""
        assert isinstance(self.move_history, list)
        assert len(self.move_history) > 0
        last_move = self.move_history.pop(-1)
        self.robots_location[last_move[0]] = last_move[2]
        return last_move

    def move_history_by_robot(self, robot):
        """Utility for returning a robots most recent move"""
        assert isinstance(self.move_history, list)
        last_move = None
        for move in self.move_history:
            if move[0] == robot:
                last_move = move
        return last_move

    def robot_by_cell(self, cell):
        """Utility for finding robot by value instead of key"""
        assert isinstance(self.robots_location, dict)
        for robot in self.robots_location:
            if self.robots_location[robot] == cell:
                return robot

    def goal(self):
        """Current goal if one available - used for display"""
        assert self.game_state == State.play
        return self.board_section.goals[self.goal_index]

    def __move(self, robot, direction):
        """request to move 'robot' in 'direction'"""
        last_move = self.move_history_by_robot(robot)
        if self.is_perpendicular_mode:
            if last_move is not None and last_move[1] in (direction, direction.reverse()):
                return PPMoveStatus.PERPENDICULAR_MOVE_REQUIRED
        point = self.robots_location[robot]
        goal = self.board_section.goals[self.goal_index]
        new_cell = self.__cell_move(
            point,
            direction,
            robot)
        if point == new_cell:
            return PPMoveStatus.CANNOT_MOVE_DIRECTION
        elif self.is_perpendicular_mode and last_move is None and new_cell == goal.point and robot in goal.robots:
            return PPMoveStatus.PERPENDICULAR_BEFORE_GOAL
        else:
            return new_cell

    def robot_moves(self, robot=None):
        """Return list of possible moves filtered by 'robot'"""
        assert robot is None or robot in Shared.ROBOTS
        if robot:
            robots = [robot]
        else:
            robots = Shared.ROBOTS
        moves = []
        for bot in robots:
            point = self.robots_location[bot]
            for direction in Shared.DIRECTIONS:
                new_cell = self.__move(bot, direction)
                if isinstance(new_cell, Point):
                    moves.append((bot, direction, point, new_cell))
        return moves

    def robot_move(self, robot, direction):
        """request to move 'robot' in 'direction'"""
        assert self.game_state == State.play
        new_cell = self.__move(robot, direction)
        if isinstance(new_cell, int):
            return new_cell
        else:
            self.move_history.append((robot, direction, self.robots_location[robot], new_cell))
            self.robots_location[robot] = new_cell
            
        #check for win condition after move - adjust game state if needed
        goal = self.goal()
        for robot in Shared.ROBOTS:
            if robot in goal.robots and goal.point == self.robots_location[robot]:
                self.level_time = time.time() - self.level_time
                self.game_time_count += self.level_time
                self.game_move_count += len(self.move_history)
                self.__robots_starting_location = {}
                for r in self.robots_location:
                    self.__robots_starting_location[r] = self.robots_location[r]
                if self.goal_index + 1 == len(self.board_section.goals):
                    self.game_state = State.game_complete
                else:
                    self.game_state = State.level_complete
                break
        return PPMoveStatus.MOVE_SUCCESS

    def level_restart(self):
        assert self.game_state == State.play
        self.move_history = []
        self.robots_location = {}
        for robot in self.__robots_starting_location:
            self.robots_location[robot] = self.__robots_starting_location[robot]

    def level_next(self):
        assert self.goal_index < len(self.board_section.goals) - 1
        self.game_state = State.level_complete
        self.level_new()

    def level_previous(self):
        assert self.goal_index > 0
        self.game_state = State.level_complete
        self.goal_index -= 2
        self.level_new()

    def level_new(self):
        """per level information: movehistory, robots"""
        assert self.game_state in [State.level_complete]
        self.goal_index += 1
        assert self.goal_index < len(self.board_section.goals)
        self.level_time = time.time()
        self.game_state = State.play
        self.level_restart()

    def game_new(self, seed=None, goal_count=None, is_perpendicular_mode=True):
        """generate board, setup goal, setup robots, start time
        seed in the format of {BoardSectionKey}*4 + ! +
        {ObjectName}[0]{Point}*4 + ! + {GoalObjectName}[0]{GoalPoint}
        Example: A1A2A3A4!R0301B0415G0005Y1213!YBGR1203|B1515
            BoardSection: A1A2A3A4
            Object Point: R0301B0415G0005Y1213
            Goal Objects: YBGR1203|B1515
        """
        self.is_perpendicular_mode = is_perpendicular_mode
        boards = []
        dimension = None
        robots = None
        goals = None
        if isinstance(seed, str) and seed:
            sections = seed.split("!")[:3]
            if sections[0][0] == "E":
                dimension = int(sections[0][1:])
            else:
                boards = sections[0]
                boards = [boards[i:i+2] for i in range(0, len(boards), 2)]

            if len(sections) > 1:
                robots = sections[1]
                robots = [(
                    Shared.robot_by_name(robots[i:i+1]),
                    Point(int(robots[i+1:i+3]), int(robots[i+3:i+5])))
                          for i in range(0, len(robots), 5)]
                for i in range(len(robots), 4):
                    robots.append("")
            if len(sections) > 2:
                goals = sections[2].split("|")
                goals = [Goal(
                    Point(int(goalstring[-4:-2]), int(goalstring[-2:])),
                    [Shared.robot_by_name(robot) for robot in goalstring[:-4]])
                         for goalstring in goals]

        if not dimension:
            for i in range(len(boards), 4):
                boards.append("")

        self.__board_generate(boards, robots, goals, dimension, goal_count, is_perpendicular_mode)
        self.goal_index = -1
        self.game_move_count = 0
        self.game_time_count = 0
        self.game_state = State.level_complete
        self.level_new()
