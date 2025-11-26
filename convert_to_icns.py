import os
import sys
from pathlib import Path
from PIL import Image
import subprocess
import tempfile
import shutil
import logging
from typing import Optional, List, Union, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

class IconConverter:
    """Clase para convertir imágenes a formatos de ícono (ICNS de macOS y ICO de Windows)"""
    
    # Tamaños estándar requeridos para ICNS (incluye @2x implícito)
    ICNS_SIZES = [16, 32, 64, 128, 256, 512, 1024]
    
    # Tamaños recomendados para ICO de Windows
    ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
    
    SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.gif', '.webp'}
    
    def __init__(self, preserve_alpha: bool = True, quality: int = 95, 
                 auto_upscale: bool = False, verbose: bool = True):
        """
        Args:
            preserve_alpha: Si True, preserva transparencia (requiere PNG)
            quality: Calidad de compresión (1-100)
            auto_upscale: Si True, escala automáticamente imágenes pequeñas
            verbose: Si True, muestra mensajes de progreso
        """
        self.preserve_alpha = preserve_alpha
        self.quality = quality
        self.auto_upscale = auto_upscale
        self.logger = logging.getLogger(__name__)
        
        if verbose:
            logging.basicConfig(
                level=logging.INFO,
                format='%(message)s'
            )
    
    @staticmethod
    def _verify_iconutil():
        """Verifica que iconutil esté disponible (solo macOS)"""
        if sys.platform != 'darwin':
            raise OSError("La conversión a ICNS solo funciona en macOS.")
        
        if shutil.which('iconutil') is None:
            raise OSError("'iconutil' no está disponible. Asegúrate de estar en macOS.")
    
    def _upscale_if_needed(self, img: Image.Image, min_size: int) -> Image.Image:
        """Escala la imagen si es menor al tamaño mínimo"""
        if min(img.size) < min_size:
            if not self.auto_upscale:
                return img
            
            self.logger.warning(f"Escalando imagen desde {img.size} a {min_size}x{min_size}")
            scale = min_size / min(img.size)
            new_size = tuple(int(dim * scale) for dim in img.size)
            return img.resize(new_size, Image.Resampling.LANCZOS)
        return img
    
    def _prepare_image(self, img: Image.Image) -> Image.Image:
        """Prepara la imagen para conversión (garantiza RGBA para transparencia)"""
        
        # Guardar metadatos
        metadata = img.info.copy() if hasattr(img, 'info') else {}
        
        # Convertir imágenes con paleta o modo simple
        if img.mode == 'P':
            img = img.convert('RGBA' if 'transparency' in img.info else 'RGB')
        
        # Convertir a RGBA para manejar la transparencia
        if self.preserve_alpha and img.mode != 'RGBA':
            prepared = img.convert('RGBA')
        # Si no se preserva alpha o la imagen no tiene, convertir a RGB
        elif not self.preserve_alpha and img.mode == 'RGBA':
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            prepared = background.convert('RGB')
        else:
            prepared = img
        
        # Restaurar metadatos importantes
        if metadata:
            prepared.info = metadata
        
        return prepared
    
    def _create_iconset(self, img: Image.Image, iconset_dir: Path) -> None:
        """Crea el conjunto de íconos .png para iconutil (solo ICNS)"""
        iconset_dir.mkdir(parents=True, exist_ok=True)
        
        # Cachear tamaños ya procesados para reutilizar
        size_cache = {}
        
        for size in self.ICNS_SIZES:
            # Versión estándar
            if size not in size_cache:
                size_cache[size] = img.resize((size, size), Image.Resampling.LANCZOS)
            
            resized = size_cache[size]
            filename = iconset_dir / f"icon_{size}x{size}.png"
            resized.save(filename, 'PNG', optimize=True)
            
            # Versión @2x (retina) - no existe para 1024px
            if size < 512:
                double_size = size * 2
                if double_size not in size_cache:
                    size_cache[double_size] = img.resize((double_size, double_size), Image.Resampling.LANCZOS)
                
                resized_2x = size_cache[double_size]
                filename_2x = iconset_dir / f"icon_{size}x{size}@2x.png"
                resized_2x.save(filename_2x, 'PNG', optimize=True)

    def _convert_to_icns(self, prepared_img: Image.Image, output_path: Path) -> None:
        """Usa iconutil para convertir un iconset a ICNS"""
        self._verify_iconutil()

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            iconset_dir = temp_path / "icon.iconset"
            
            # Crear iconset
            self._create_iconset(prepared_img, iconset_dir)
            
            # Ejecutar iconutil
            result = subprocess.run(
                ['iconutil', '-c', 'icns', str(iconset_dir), '-o', str(output_path)],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Error al crear ICNS: {result.stderr}")

    def _convert_to_ico(self, prepared_img: Image.Image, output_path: Path) -> None:
        """Usa PIL para convertir a ICO (multiplataforma)"""
        
        # PIL soporta tamaños específicos para ICO
        sizes_tuple = [(s, s) for s in self.ICO_SIZES if s <= min(prepared_img.size)]
        
        if not sizes_tuple:
            raise ValueError("La imagen es demasiado pequeña para generar tamaños ICO estándar.")

        prepared_img.save(
            output_path, 
            format='ICO', 
            sizes=sizes_tuple, 
            quality=self.quality
        )

    def convert(self, 
                input_path: Union[str, Path], 
                target_format: str,
                output_path: Optional[Union[str, Path]] = None) -> Path:
        """
        Convierte una imagen a formato ICNS o ICO
        
        Args:
            input_path: Ruta de la imagen de entrada
            target_format: 'icns' o 'ico'
            output_path: Ruta de salida (opcional)
        
        Returns:
            Path del archivo de ícono creado
        """
        input_path = Path(input_path)
        target_format = target_format.lower()
        
        if target_format not in ['icns', 'ico']:
            raise ValueError("El formato objetivo debe ser 'icns' o 'ico'")

        if not input_path.exists():
            raise FileNotFoundError(f"El archivo {input_path} no existe")
        
        # Validar formato de entrada
        if input_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato no soportado: {input_path.suffix}. "
                f"Formatos válidos: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        
        # Determinar ruta de salida
        suffix = f".{target_format}"
        if output_path is None:
            output_path = input_path.with_suffix(suffix)
        else:
            output_path = Path(output_path).with_suffix(suffix) 
            output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Abrir, validar y copiar la imagen
        prepared_img = None
        try:
            with Image.open(input_path) as img:
                min_size = 1024 if target_format == 'icns' else max(self.ICO_SIZES)
                
                # Validar o escalar tamaño
                if min(img.size) < min_size:
                    if self.auto_upscale:
                        img = self._upscale_if_needed(img, min_size)
                    else:
                        min_required = 16 if target_format == 'ico' else min_size
                        if min(img.size) < min_required:
                            raise ValueError(
                                f"La imagen debe tener al menos {min_required}x{min_required} píxeles "
                                f"para {target_format.upper()}. Use --auto-upscale para escalar automáticamente."
                            )
                
                # Preparar imagen (manejar transparencia/modo)
                temp_prepared_img = self._prepare_image(img)
                
                # Copiar la imagen para que sea independiente
                prepared_img = temp_prepared_img.copy()

        except Exception:
            raise

        if prepared_img is None:
            raise RuntimeError("Fallo al cargar la imagen.")

        # Llamar al conversor específico
        if target_format == 'icns':
            self._convert_to_icns(prepared_img, output_path)
        elif target_format == 'ico':
            self._convert_to_ico(prepared_img, output_path)
        
        # Cerrar la imagen preparada
        prepared_img.close()
        
        self.logger.info(f"✓ Creado: {output_path.name}")
        return output_path
    
    def _check_disk_space(self, image_files: List[Path], output_folder: Path) -> None:
        """Verifica que hay suficiente espacio en disco"""
        total_size = sum(f.stat().st_size for f in image_files)
        estimated_output = total_size * 1.5  # Estimación conservadora
        
        free_space = shutil.disk_usage(output_folder).free
        if free_space < estimated_output:
            raise OSError(
                f"Espacio insuficiente: {free_space / 1e9:.1f}GB disponibles, "
                f"~{estimated_output / 1e9:.1f}GB necesarios estimados"
            )
    
    def batch_convert(self, 
                      input_folder: Union[str, Path], 
                      target_format: str,
                      output_folder: Optional[Union[str, Path]] = None,
                      recursive: bool = False,
                      max_workers: int = 4,
                      dry_run: bool = False) -> List[Path]:
        """
        Convierte múltiples imágenes en paralelo
        
        Args:
            input_folder: Carpeta con imágenes
            target_format: 'icns' o 'ico'
            output_folder: Carpeta de salida (opcional)
            recursive: Buscar en subcarpetas
            max_workers: Número de conversiones paralelas
            dry_run: Si True, solo muestra qué archivos se procesarían
        
        Returns:
            Lista de archivos de ícono creados
        """
        input_folder = Path(input_folder)
        target_format = target_format.lower()
        
        if target_format not in ['icns', 'ico']:
            raise ValueError("El formato objetivo debe ser 'icns' o 'ico'")

        if not input_folder.exists():
            raise FileNotFoundError(f"La carpeta {input_folder} no existe")
        
        # Determinar carpeta de salida
        if output_folder is None:
            output_folder = input_folder
        else:
            output_folder = Path(output_folder)
            output_folder.mkdir(parents=True, exist_ok=True)
        
        # Encontrar archivos
        pattern = '**/*' if recursive else '*'
        image_files = [
            f for f in input_folder.glob(pattern)
            if f.is_file() and f.suffix.lower() in self.SUPPORTED_FORMATS
        ]
        
        if not image_files:
            self.logger.info("No se encontraron imágenes para convertir")
            return []
        
        # Modo dry-run
        if dry_run:
            self.logger.info(f"\n[Dry run] Se procesarían {len(image_files)} archivos:")
            for img in image_files:
                output_name = img.with_suffix(f'.{target_format}').name
                self.logger.info(f"  • {img.name} → {output_name}")
            return []
        
        # Verificar espacio en disco
        try:
            self._check_disk_space(image_files, output_folder)
        except OSError as e:
            self.logger.warning(str(e))
        
        self.logger.info(f"Encontradas {len(image_files)} imágenes. Convirtiendo a .{target_format}...")
        
        # Conversión en paralelo
        converted = []
        failed = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Crear tareas
            future_to_file = {
                executor.submit(
                    self.convert,
                    img_file,
                    target_format,
                    output_folder / img_file.with_suffix(f'.{target_format}').name
                ): img_file
                for img_file in image_files
            }
            
            # Procesar resultados
            for future in as_completed(future_to_file):
                img_file = future_to_file[future]
                try:
                    result_path = future.result()
                    converted.append(result_path)
                except Exception as e:
                    failed.append((img_file.name, str(e)))
                    self.logger.error(f"✗ Error en {img_file.name}: {e}")
        
        # Resumen
        self.logger.info(f"\n{'='*50}")
        self.logger.info(f"Conversión a .{target_format} completada:")
        self.logger.info(f"  ✓ Exitosas: {len(converted)}")
        if failed:
            self.logger.info(f"  ✗ Fallidas: {len(failed)}")
            self.logger.info(f"\nErrores detallados:")
            for filename, error in failed:
                self.logger.info(f"  • {filename}: {error}")
        self.logger.info(f"{'='*50}")
        
        return converted


def main():
    """Función principal para uso desde línea de comandos"""
    
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Convierte imágenes a formatos de ícono (ICNS de macOS y ICO de Windows).',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Convertir a ICNS (requiere macOS)
  %(prog)s icon.png
  %(prog)s icon.png -f icns -o ~/Desktop/mi_icono.icns
  
  # Convertir a ICO (multiplataforma)
  %(prog)s icon.png -f ico
  %(prog)s ./imagenes/ -f ico -r --workers 8
  
  # Previsualizar sin convertir
  %(prog)s ./imagenes/ -f ico --dry-run
  
  # Escalar automáticamente imágenes pequeñas
  %(prog)s small_icon.png -f icns --auto-upscale
        """
    )
    
    parser.add_argument('input', help='Archivo de imagen o directorio')
    parser.add_argument('-o', '--output', help='Archivo o directorio de salida (sin extensión)')
    parser.add_argument('-f', '--format', default='icns', choices=['icns', 'ico'],
                       help='Formato de ícono de salida: icns (macOS) o ico (Windows/Web). Default: icns')
    parser.add_argument('-r', '--recursive', action='store_true',
                       help='Buscar imágenes en subcarpetas')
    parser.add_argument('--no-alpha', action='store_true',
                       help='No preservar transparencia')
    parser.add_argument('--auto-upscale', action='store_true',
                       help='Escalar automáticamente imágenes menores al tamaño mínimo')
    parser.add_argument('-w', '--workers', type=int, default=4,
                       help='Número de conversiones paralelas (default: 4)')
    parser.add_argument('-q', '--quality', type=int, default=95,
                       help='Calidad de compresión 1-100 (solo para ICO). Default: 95')
    parser.add_argument('--dry-run', action='store_true',
                       help='Previsualizar archivos a procesar sin convertirlos')
    parser.add_argument('--quiet', action='store_true',
                       help='No mostrar mensajes de progreso')
    
    args = parser.parse_args()
    
    try:
        converter = IconConverter(
            preserve_alpha=not args.no_alpha,
            quality=args.quality,
            auto_upscale=args.auto_upscale,
            verbose=not args.quiet
        )
        
        input_path = Path(args.input)
        
        if input_path.is_file():
            converter.convert(input_path, args.format, args.output)
        elif input_path.is_dir():
            converter.batch_convert(
                input_path,
                args.format,
                args.output,
                recursive=args.recursive,
                max_workers=args.workers,
                dry_run=args.dry_run
            )
        else:
            print(f"Error: {args.input} no es un archivo o directorio válido")
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()