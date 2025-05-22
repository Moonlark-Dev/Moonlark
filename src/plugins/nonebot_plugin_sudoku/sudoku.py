import random

problem=[]
answer=[]

class Sudoku():
    def __init__(self):
        self.arrays = [0] * 81

    def array(self, row_array):
        array = {1, 2, 3, 4, 5, 6, 7, 8, 9}
        little_array = [0,  1,  2,
                        9, 10, 11,
                       18, 19, 20]
        little_array = [little_array1 + 3 * row_array for little_array1 in little_array]

        for i in little_array:
            if self.arrays[i] != 0 and array:
                array.remove(self.arrays[i])

        for i in little_array:
            array_copy = array.copy()
            if self.arrays[i] == 0:
                row = self.arrays[i // 9 * 9:i // 9 * 9 + 9].copy()
                array = array.difference(set(row))

                column = []
                for column_i in range(9):
                    column.append(self.arrays[(i % 9) + 9*column_i])
                array = array.difference(set(column))
                if array:
                    x = random.choice(list(array))
                    self.arrays[i] = x
                    array.remove(x)
                    array_copy.remove(x)
                    array = array_copy.copy()

    def sudoku(self):
        for row_array in [0, 1, 2, 9, 10, 11, 18, 19, 20]:
            self.array(row_array)
        return self.arrays
    
def generate_new(num_holes: int):
    global problem, answer
    for null in range(10000):
        answer = Sudoku().sudoku()
        if 0 not in answer:
            break
    problem = answer.copy()
    for i in range(num_holes):
        flag=True
        while flag:
            x, y=random.randint(0,8), random.randint(0,8)
            if problem[y*9+x]!=0:
                problem[y*9+x]=0
                flag=False

def get_problem():
    global problem
    src = problem
    content = {"rows": [[[[0 for i in range(3)] for i in range(3)] for i in range(3)] for i in range(3)]}
    for i in range(len(src)):
        content["rows"][(i//9)//3][(i%9)//3][(i//9)%3][(i%9)%3] = ("" if src[i]==0 else str(src[i]))
    return content

def get_answer():
    global answer
    src = answer
    content = {"rows": [[[[0 for i in range(3)] for i in range(3)] for i in range(3)] for i in range(3)]}
    for i in range(len(src)):
        content["rows"][(i//9)//3][(i%9)//3][(i//9)%3][(i%9)%3] = ("" if src[i]==0 else str(src[i]))
    return content

