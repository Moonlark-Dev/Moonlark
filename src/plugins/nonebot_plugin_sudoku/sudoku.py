import random
from nonebot import get_driver, logger

problem=[]
current=[]
answer=[]
operations=[]
operation_index=-1

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
    global problem, answer, current
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
    current = problem.copy()

def get_problem():
    global problem
    src = problem
    content = {"rows": [[[[0 for i in range(3)] for i in range(3)] for i in range(3)] for i in range(3)]}
    for i in range(len(src)):
        content["rows"][(i//9)//3][(i%9)//3][(i//9)%3][(i%9)%3] = ("" if src[i]==0 else str(src[i]))
    return content

def get_current():
    global current
    src = current
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

def change(x: int, y: int, value: int):
    global current, operations, operation_index
    current[(y-1)*9+x-1] = value
    if(len(operations) > -1):
        operations = operations[0 : operation_index+1]
    operations.append(["change", x, y, value])
    operation_index+=1

def erase(x: int, y: int):
    global current, operations, operation_index
    if(len(operations) > -1):
        operations = operations[0 : operation_index+1]
    operations.append(["erase", x, y, current[(y-1)*9+x-1]])
    current[(y-1)*9+x-1] = 0
    operation_index+=1

def hint():
    global answer, current
    for i in range(len(answer)):
        if current[i] == 0:
            current[i] = answer[i]
            break

def reset():
    global problem, current, operations, operation_index
    if(len(operations) > -1):
        operations = operations[0 : operation_index+1]
    operations.append(["reset", current.copy()])
    current = problem.copy()
    operation_index+=1

def able_to_change(x: int, y: int):
    return problem[(y-1)*9+x-1] == 0

def able_to_undo():
    return operation_index > -1

def able_to_redo():
    return operation_index < len(operations)-1

def conflict(x: int, y: int, value: int):
    set1 = {value,}
    set2 = {value,}
    set3 = {value,}
    tot1 = tot2 = tot3 = 1
    for i in range(9):
        v = current[(y-1)*9+i]
        if v != 0:
            set1.add(v)
            tot1 += 1
    for i in range(9):
        v = current[i*9+(x-1)]
        if v != 0:
            set2.add(v)
            tot2 += 1
    for i in range(3):
        for j in range(3):
            v=current[(((y-1)//3)*3+j)*9+(((x-1)//3)*3+i)]
            if v != 0:
                set3.add(v)
                tot3 += 1
    logger.info(set1)
    logger.info(set2)
    logger.info(set3)
    return len(set1) != tot1 or len(set2) != tot2 or len(set3) != tot3

def undo():
    global operations, operation_index, current
    operation = operations[operation_index]
    operation_index-=1
    if operation[0] == "change":
        x, y = operation[1], operation[2]
        current[(y-1)*9+x-1] = 0
    elif operation[0] == "erase":
        x, y, value = operation[1], operation[2], operation[3]
        current[(y-1)*9+x-1] = value
    else:
        value = operation[1]
        current = value.copy()
    
def redo():
    global operations, operation_index, current, problem
    operation_index+=1
    operation = operations[operation_index]
    if operation[0] == "change":
        x, y, value = operation[1], operation[2], operation[3]
        current[(y-1)*9+x-1] = value
    elif operation[0] == "erase":
        x, y = operation[1], operation[2]
        current[(y-1)*9+x-1] = 0
    else:
        current = problem.copy()

def view_problem():
    src = list(map(str,problem))
    for i in range(9):
        line=src[i*9 : i*9+9]
        logger.log("INFO", " ".join(line))

def view_current():
    src = list(map(str,current))
    for i in range(9):
        line=src[i*9 : i*9+9]
        logger.log("INFO", " ".join(line))

def view_answer():
    src = list(map(str,answer))
    for i in range(9):
        line=src[i*9 : i*9+9]
        logger.log("INFO", " ".join(line))

'''
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 0 2 4 1 5 7 3 6 9
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 0 0 9 2 0 0 4 0 7
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 5 0 0 4 9 0 2 1 0
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 2 1 3 0 7 5 9 4 6
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 4 8 5 6 1 9 0 3 2
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 7 9 6 3 0 4 1 8 0
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 3 5 1 9 0 2 8 7 0
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 9 0 8 5 4 0 6 2 1
05-24 23:44:28 [INFO] nonebot_plugin_sudoku | 0 4 2 7 8 1 0 9 3


'''