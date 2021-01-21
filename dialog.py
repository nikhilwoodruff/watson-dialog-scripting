import json
import re
import argparse
import csv

class Intent:
    def __init__(self, id, *examples):
        self.id = id
        self.examples = examples
    
    def encode(self):
        encoded = dict(
            intent=self.id,
            examples=[dict(text=example) for example in self.examples]
        )
        return encoded

class StoryNodePointer:
    def __init__(self, source, target, condition, previous_sibling):
        self.source = source
        self.target = target
        self.conditions = condition
        self.previous_sibling = previous_sibling
        self.id = self.source.id + "-" + self.target.id
    
    def encode(self):
        node = dict(
            type="standard",
            title=self.target.id,
            parent=self.source.id,
            next_step=dict(
                behavior="jump_to",
                selector="condition",
                dialog_node=self.target.id
            ),
            context=dict(),
            dialog_node=self.id,
            conditions=self.conditions
        )
        if self.previous_sibling is not None:
            node["previous_sibling"] = self.previous_sibling.id
        return node

class StoryNode:
    def __init__(self, id, text, responses, children):
        self.id = id
        self.text = text
        self.children = {response : child for response, child in zip(responses, children)}
        self.parent = None
        self.previous_sibling = None
        self.conditions = None

    def encode(self):
        node = dict(
            type="standard",
            title=self.id,
            output=dict(
                generic=[dict(
                    values=[dict(
                        text=f"<speak>{self.text}</speak>"
                    )],
                    response_type="text",
                    selection_policy="sequential"
                )]
            ),
            context=dict(),
            dialog_node=self.id
        )
        if self.parent is not None:
            node["parent"] = self.parent.id
        if self.previous_sibling is not None:
            node["previous_sibling"] = self.previous_sibling.id
        if self.conditions is not None:
            node["conditions"] = self.conditions
        return node
        

    def tree(self, story_nodes):
        nodes = [self]
        previous_sibling = None
        for response in self.children.keys():
            is_pointer = False
            child = story_nodes[self.children[response]]
            if child.parent is None:
                child.parent = story_nodes[self.id]
            else:
                child = StoryNodePointer(self, child, response, previous_sibling)
                is_pointer = True
            if previous_sibling is not None:
                child.previous_sibling = previous_sibling
            previous_sibling = child
            child.conditions = response
            if not is_pointer:
                nodes += child.tree(story_nodes)
            else:
                nodes += [child]
        return nodes

class StoryTree:
    def __init__(self, filename=None):
        self.nodes = []
        if filename is not None:
            self.load_from_csv(filename)
    
    def set_voice_map(self, **voices):
        self.voices = voices
    
    def load_from_csv(self, filename):
        self.nodes = []
        with open(filename, "r") as f:
            reader = csv.reader(f)
            for line in reader:
                line = list(filter(lambda field : field != "", line))
                id, text, = line[0], line[1]
                node = StoryNode(id, text, [], [])
                num_responses = (len(line) - 2) // 2
                if num_responses > 0:
                    behaviour = line[2:]
                for response, child in zip(behaviour[:num_responses], behaviour[num_responses:]):
                    node.children[response] = child
                self.nodes += [node]
    
    def load_from_console(self):
        id = input("Node ID: ")
        if id == "":
            return
        node = StoryNode(id, input("Node text: "), [], [])
        response = input("First response: ")
        while response != "":
            child = input("Child: ")
            node.children[response] = child
            response = input("Next response: ")
        return node
    
    def load_voice_file(self, filename):
        self.voices = {}
        with open(filename, "r") as f:
            for line in f.readlines():
                name, voice_name = line[:-1].split(",")
                self.voices[name] = voice_name
    
    def export(self):
        responses = []
        for node in self.nodes:
            if len(node.children) > 0:
                node.text += "\nDo you: \n"
            for response in node.children.keys():
                responses += [response]
                node.text += response + "?\n"
        responses = list(set(responses))
        intents = []
        response_to_intent = {}
        for i in range(len(responses)):
            if responses[i] not in ["conversation_start", "anything_else"]:
                safe_response = responses[i].replace(" ", "_").replace("'", "_")
                intent = Intent(safe_response, responses[i])
                intents += [intent.encode()]
                response_to_intent[responses[i]] = "#" + safe_response
        for node in self.nodes:
            new_responses = {}
            for response, child in node.children.items():
                if response not in ["conversation_start", "anything_else"]:
                    new_responses[response_to_intent[response]] = child
                else:
                    new_responses[response] = child
            node.children = new_responses
            for name, voice_name in self.voices.items():
                node.text = re.sub(f'\[{name}\](\".*\")', f'<voice name=\"{voice_name}\">\\1</voice>', node.text)
        nodes = {node.id : node for node in self.nodes}
        tree = nodes[list(nodes.keys())[0]].tree(nodes)
        tree[0].conditions = "conversation_start"
        dialog_nodes = [node.encode() for node in tree]
        encoded = dict(
            intents=intents,
            entities=[],
            metadata=dict(
                api_version=dict(
                    major_version="v2",
                    minor_version="2018-11-08"
                ),
            ),
            webhooks=[dict(
                url="",
                name="main_webhook",
                headers=[]
            )],
            dialog_nodes=dialog_nodes,
            counterexamples=[],
            system_settings=dict(
                off_topic=dict(
                    enabled=False
                ),
                disambiguation=dict(
                    prompt="Did you mean:",
                    enabled=True,
                    randomize=True,
                    max_suggestions=5,
                    suggestion_text_policy="user_label",
                    none_of_the_above_prompt="None of the above."
                ),
                system_entities=dict(
                    enabled=True
                ),
                human_agent_assist=dict(
                    prompt="Did you mean:"
                ),
                intent_classification=dict(
                    training_backend_version="v2"
                ),
                spelling_auto_correct=True
            ),
            learning_opt_out=False,
            name="Scripted Dialog",
            language="en",
            description=""
        )
        return json.dumps(encoded)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Utility for converting dialogue scripts into IBM Watson Dialog Skills.")
    parser.add_argument("dialog_file", help="A CSV file with rows containing node ID, node text, *possible responses, *next nodes.")
    parser.add_argument("--voice_file", help="A CSV file with a row for each alias, SSML voice name pair. Aliases are encoded into SSML when found as [Alias]\"speech\".")
    parser.add_argument("--output", help="The output file to write to.", default="dialog.json")
    args = parser.parse_args()
    tree = StoryTree(filename=args.dialog_file)
    if args.voice_file is not None:
        tree.load_voice_file(args.voice_file)
    with open(args.output, "w+", encoding="utf-8") as f:
        f.write(tree.export())
    print(f"Completed, output saved in {args.output}.")