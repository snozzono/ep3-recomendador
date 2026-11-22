# Lanza el job de entrenamiento ALS en SageMaker. Ejecutar desde CloudShell (requiere sagemaker<3).
import os

import sagemaker
from sagemaker.sklearn.estimator import SKLearn

BUCKET = os.environ.get("BUCKET", "ep2-equipo1-128688195152")
ROLE = os.environ.get("ROLE_ARN", "arn:aws:iam::128688195152:role/LabRole")
DATOS = f"s3://{BUCKET}/datos/amazon-industrial/"
SALIDA = f"s3://{BUCKET}/sagemaker-output/"
HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    sesion = sagemaker.Session(default_bucket=BUCKET)
    estimador = SKLearn(
        entry_point="02_entrenar_sagemaker.py",
        source_dir=HERE,
        framework_version="1.2-1",
        py_version="py3",
        role=ROLE,
        instance_type="ml.t3.large",
        instance_count=1,
        output_path=SALIDA,
        base_job_name="ep3-svd",
        hyperparameters={"k": 32},
        sagemaker_session=sesion,
    )
    estimador.fit({"datos": DATOS}, wait=True, logs=True)
    print("TRAINING_JOB =", estimador.latest_training_job.name)


if __name__ == "__main__":
    main()
