import random

class Sudoku():
    def __init__(self):
        self.arrays = [0] * 81
    def view(self, arrays):
        for index in range(len(arrays)):
            if index > 0 and index % 9 == 0:
                print('\n', end='')
            print(arrays[index], end=' ')
        print('\n')

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
for null in range(10000):
    arrays = Sudoku().sudoku()
    if 0 not in arrays:
        Sudoku().view(arrays)
        break