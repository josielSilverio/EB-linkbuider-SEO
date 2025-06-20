import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Tuple, Optional

class DBHandler:
    def __init__(self, db_path: str = "data/titles_learning.db"):
        """
        Inicializa o handler do banco de dados.
        
        Args:
            db_path: Caminho para o arquivo do banco de dados SQLite
        """
        self.db_path = db_path
        self.logger = logging.getLogger('seo_linkbuilder.db')
        self._init_db()
        
    def _init_db(self):
        """Inicializa as tabelas do banco de dados se não existirem."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Tabela de títulos
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS titles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    anchor_word TEXT NOT NULL,
                    main_theme TEXT NOT NULL,
                    structure_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    performance_score FLOAT DEFAULT 0.0,
                    feedback_score FLOAT DEFAULT 0.0,
                    is_approved BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Tabela de temas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS themes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title_id INTEGER,
                    theme TEXT NOT NULL,
                    FOREIGN KEY (title_id) REFERENCES titles (id)
                )
            """)
            
            # Tabela de estruturas bem-sucedidas
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS successful_structures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    structure_pattern TEXT NOT NULL,
                    theme TEXT NOT NULL,
                    success_count INTEGER DEFAULT 1,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
    
    def add_title(self, title: str, anchor_word: str, main_theme: str, structure_type: str, themes: List[str]) -> int:
        """
        Adiciona um novo título ao banco de dados.
        
        Args:
            title: O título gerado
            anchor_word: A palavra-âncora usada
            main_theme: O tema principal do título
            structure_type: O tipo de estrutura usado
            themes: Lista de temas secundários
            
        Returns:
            ID do título inserido
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Insere o título
                cursor.execute("""
                    INSERT INTO titles (title, anchor_word, main_theme, structure_type)
                    VALUES (?, ?, ?, ?)
                """, (title, anchor_word, main_theme, structure_type))
                
                title_id = cursor.lastrowid
                
                # Insere os temas
                for theme in themes:
                    cursor.execute("""
                        INSERT INTO themes (title_id, theme)
                        VALUES (?, ?)
                    """, (title_id, theme))
                
                conn.commit()
                return title_id
                
        except Exception as e:
            self.logger.error(f"Erro ao adicionar título: {e}")
            raise
    
    def update_title_performance(self, title_id: int, performance_score: float, feedback_score: float = None):
        """
        Atualiza as métricas de desempenho de um título.
        
        Args:
            title_id: ID do título
            performance_score: Pontuação de desempenho (0-1)
            feedback_score: Pontuação de feedback opcional (0-1)
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                if feedback_score is not None:
                    cursor.execute("""
                        UPDATE titles
                        SET performance_score = ?, feedback_score = ?
                        WHERE id = ?
                    """, (performance_score, feedback_score, title_id))
                else:
                    cursor.execute("""
                        UPDATE titles
                        SET performance_score = ?
                        WHERE id = ?
                    """, (performance_score, title_id))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Erro ao atualizar desempenho do título: {e}")
            raise
    
    def get_successful_patterns(self, theme: str, limit: int = 5) -> List[Dict]:
        """
        Retorna os padrões de estrutura mais bem-sucedidos para um tema.
        
        Args:
            theme: O tema principal
            limit: Número máximo de padrões a retornar
            
        Returns:
            Lista de dicionários com padrões e suas pontuações
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT structure_pattern, success_count
                    FROM successful_structures
                    WHERE theme = ?
                    ORDER BY success_count DESC, last_used DESC
                    LIMIT ?
                """, (theme, limit))
                
                return [
                    {"pattern": row[0], "success_count": row[1]}
                    for row in cursor.fetchall()
                ]
                
        except Exception as e:
            self.logger.error(f"Erro ao buscar padrões de sucesso: {e}")
            return []
    
    def update_structure_success(self, structure_pattern: str, theme: str):
        """
        Atualiza o contador de sucesso para uma estrutura específica.
        
        Args:
            structure_pattern: O padrão de estrutura
            theme: O tema principal
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO successful_structures (structure_pattern, theme)
                    VALUES (?, ?)
                    ON CONFLICT (structure_pattern, theme) DO UPDATE
                    SET success_count = success_count + 1,
                        last_used = CURRENT_TIMESTAMP
                """, (structure_pattern, theme))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"Erro ao atualizar sucesso da estrutura: {e}")
            raise
    
    def get_similar_successful_titles(self, anchor_word: str, theme: str, limit: int = 5) -> List[Dict]:
        """
        Retorna títulos bem-sucedidos similares baseados na palavra-âncora e tema.
        
        Args:
            anchor_word: A palavra-âncora
            theme: O tema principal
            limit: Número máximo de títulos a retornar
            
        Returns:
            Lista de dicionários com títulos e suas métricas
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT t.title, t.performance_score, t.feedback_score
                    FROM titles t
                    WHERE t.anchor_word = ?
                        AND t.main_theme = ?
                        AND (t.performance_score > 0.7 OR t.feedback_score > 0.7)
                    ORDER BY (t.performance_score + COALESCE(t.feedback_score, 0))/2 DESC
                    LIMIT ?
                """, (anchor_word, theme, limit))
                
                return [
                    {
                        "title": row[0],
                        "performance": row[1],
                        "feedback": row[2]
                    }
                    for row in cursor.fetchall()
                ]
                
        except Exception as e:
            self.logger.error(f"Erro ao buscar títulos similares: {e}")
            return []
    
    def get_theme_statistics(self, theme: str) -> Dict:
        """
        Retorna estatísticas de desempenho para um tema específico.
        
        Args:
            theme: O tema principal
            
        Returns:
            Dicionário com estatísticas do tema
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_titles,
                        AVG(performance_score) as avg_performance,
                        AVG(feedback_score) as avg_feedback,
                        COUNT(CASE WHEN is_approved = 1 THEN 1 END) as approved_count
                    FROM titles
                    WHERE main_theme = ?
                """, (theme,))
                
                row = cursor.fetchone()
                return {
                    "total_titles": row[0],
                    "avg_performance": row[1] or 0.0,
                    "avg_feedback": row[2] or 0.0,
                    "approved_count": row[3]
                }
                
        except Exception as e:
            self.logger.error(f"Erro ao buscar estatísticas do tema: {e}")
            return {
                "total_titles": 0,
                "avg_performance": 0.0,
                "avg_feedback": 0.0,
                "approved_count": 0
            } 