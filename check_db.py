import sqlite3
import os

def check_db():
    db_path = os.path.join('data', 'titles_learning.db')
    
    if not os.path.exists(db_path):
        print("Banco de dados não encontrado!")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar tabelas existentes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        print("\nTabelas encontradas:")
        for table in tables:
            print(f"- {table[0]}")
            
        # Verificar total de títulos
        cursor.execute("SELECT COUNT(*) FROM titles")
        total = cursor.fetchone()[0]
        print(f"\nTotal de títulos armazenados: {total}")
        
        if total > 0:
            # Mostrar alguns títulos de exemplo
            cursor.execute("""
                SELECT title, performance_score, feedback_score, main_theme 
                FROM titles 
                LIMIT 5
            """)
            print("\nExemplos de títulos armazenados:")
            for row in cursor.fetchall():
                print(f"\nTítulo: {row[0]}")
                print(f"Performance: {row[1]}")
                print(f"Feedback: {row[2]}")
                print(f"Tema principal: {row[3]}")
                
            # Verificar estruturas bem-sucedidas
            cursor.execute("SELECT COUNT(*) FROM successful_structures")
            total_structures = cursor.fetchone()[0]
            print(f"\nTotal de estruturas bem-sucedidas: {total_structures}")
            
            if total_structures > 0:
                cursor.execute("""
                    SELECT structure_pattern, theme, success_count 
                    FROM successful_structures 
                    ORDER BY success_count DESC 
                    LIMIT 3
                """)
                print("\nTop 3 estruturas mais bem-sucedidas:")
                for row in cursor.fetchall():
                    print(f"\nPadrão: {row[0]}")
                    print(f"Tema: {row[1]}")
                    print(f"Contagem de sucesso: {row[2]}")
        
    except sqlite3.Error as e:
        print(f"Erro ao acessar o banco de dados: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_db() 