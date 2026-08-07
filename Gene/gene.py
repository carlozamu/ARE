class Gene:
    """
    Represents a single shot in a prompt.
    Contains both the macro attribute (hop_level) and the micro attribute (example_id),
    along with the specific text needed to construct the LLM context.
    """
    def __init__(self, hop_level: int, example_id: int, problem: str, answer: str, names: tuple[str, str]):
        self.hop_level = hop_level
        self.example_id = example_id
        self.problem = problem
        self.answer = answer
        self.names = names

    def copy(self) -> 'Gene':
        return Gene(self.hop_level, self.example_id, self.problem, self.answer, self.names)

    def __repr__(self) -> str:
        return f"Gene(hop={self.hop_level}, id={self.example_id}, problem={self.problem}, answer={self.answer}, names={self.names})"