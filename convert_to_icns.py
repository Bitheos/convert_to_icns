import os
import sys
from PIL import Image
import subprocess
import tempfile
import shutil

def convert_to_icns(input_path, output_path=None):
    """
    Convierte una imagen a formato ICNS (macOS icon)
    
    Args:
        input_path (str): Ruta de la imagen de entrada
        output_path (str, optional): Ruta de salida para el archivo .icns
    
    Returns:
        str: Ruta del archivo .icns creado
    """
    
    # Verificar que el archivo de entrada existe
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"El archivo {input_path} no existe")
    
    # Si no se especifica output_path, usar el mismo nombre con extensión .icns
    if output_path is None:
        base_name = os.path.splitext(input_path)[0]
        output_path = base_name + '.icns'
    
    # Crear directorio temporal para las imágenes de diferentes tamaños
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Tamaños requeridos para ICNS (en píxeles)
        sizes = [16, 32, 64, 128, 256, 512, 1024]
        
        # Abrir imagen original
        with Image.open(input_path) as img:
            # Convertir a RGB si es necesario (para PNG con transparencia)
            if img.mode in ('RGBA', 'LA', 'P'):
                # Crear fondo blanco para imágenes con transparencia
                background = Image.new('RGB', img.size, 'white')
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Crear imágenes en diferentes tamaños
            iconset_dir = os.path.join(temp_dir, "icon.iconset")
            os.makedirs(iconset_dir)
            
            for size in sizes:
                # Redimensionar manteniendo la relación de aspecto
                resized_img = img.resize((size, size), Image.Resampling.LANCZOS)
                
                # Guardar en diferentes formatos requeridos por ICNS
                if size in [16, 32, 128, 256, 512]:
                    # Para algunos tamaños, macOS espera versiones @2x
                    resized_img.save(os.path.join(iconset_dir, f"icon_{size}x{size}.png"))
                    if size <= 512:  # No hay @2x para 1024px
                        resized_img_2x = img.resize((size*2, size*2), Image.Resampling.LANCZOS)
                        resized_img_2x.save(os.path.join(iconset_dir, f"icon_{size}x{size}@2x.png"))
        
        # Usar el comando 'iconutil' de macOS para crear el archivo ICNS
        cmd = ['iconutil', '-c', 'icns', iconset_dir, '-o', output_path]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"Error al crear ICNS: {result.stderr}")
        
        print(f"Archivo ICNS creado exitosamente: {output_path}")
        return output_path
        
    except Exception as e:
        raise Exception(f"Error en la conversión: {str(e)}")
    
    finally:
        # Limpiar directorio temporal
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

def batch_convert_to_icns(input_folder, output_folder=None):
    """
    Convierte todas las imágenes en una carpeta a formato ICNS
    
    Args:
        input_folder (str): Carpeta con imágenes de entrada
        output_folder (str, optional): Carpeta de salida para archivos .icns
    """
    
    if not os.path.exists(input_folder):
        raise FileNotFoundError(f"La carpeta {input_folder} no existe")
    
    if output_folder is None:
        output_folder = input_folder
    elif not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    # Extensiones de imagen soportadas
    supported_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.tif', '.gif'}
    
    converted_files = []
    
    for filename in os.listdir(input_folder):
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext in supported_extensions:
            input_path = os.path.join(input_folder, filename)
            output_filename = os.path.splitext(filename)[0] + '.icns'
            output_path = os.path.join(output_folder, output_filename)
            
            try:
                convert_to_icns(input_path, output_path)
                converted_files.append(output_filename)
            except Exception as e:
                print(f"Error convirtiendo {filename}: {str(e)}")
    
    print(f"\nConversión completada. Archivos convertidos: {len(converted_files)}")
    return converted_files

def main():
    """Función principal para uso desde línea de comandos"""
    
    if len(sys.argv) < 2:
        print("Uso: python convert_to_icns.py <archivo_imagen|directorio> [archivo_salida]")
        print("\nEjemplos:")
        print("  python convert_to_icns.py icon.png")
        print("  python convert_to_icns.py icon.png ~/Desktop/mi_icono.icns")
        print("  python convert_to_icns.py ./imagenes/")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    try:
        if os.path.isfile(input_path):
            # Convertir un solo archivo
            convert_to_icns(input_path, output_path)
        elif os.path.isdir(input_path):
            # Convertir todos los archivos en el directorio
            batch_convert_to_icns(input_path, output_path)
        else:
            print(f"Error: {input_path} no es un archivo o directorio válido")
            sys.exit(1)
            
    except Exception as e:
        print(f"cd Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()